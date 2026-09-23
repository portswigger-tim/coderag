"""Effectiveness harness.

The headline number is not recall. It is the token cost of getting a correct
answer, measured against what the naive path -- grep, then open the most
promising files -- would have cost. Recall is carried alongside as a floor,
because a tool can always be made cheaper by returning less and the two
numbers together make that impossible to pass off as an improvement.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from coderag import db
from coderag.context import file_context, symbol_context, what_breaks, what_tests
from coderag.pack import estimate_tokens
from coderag.retriever import search as run_search

@dataclass
class Result:
    id: str
    question: str
    baseline_tokens: int = 0
    coderag_tokens: int = 0
    recall: float = 1.0
    passed: bool = True
    detail: str = ""

    @property
    def reduction(self) -> float:
        if self.coderag_tokens == 0:
            return 0.0
        return self.baseline_tokens / self.coderag_tokens


def _grep_baseline(root: Path, pattern: str, read_files: int) -> int:
    """Tokens an agent would burn greping then opening the top matches.

    Deliberately charitable to the baseline: it counts the grep output plus
    only the first `read_files` matching files, not every file that matched.
    """
    if not pattern:
        return 0
    try:
        proc = subprocess.run(
            ["grep", "-rn", "--binary-files=without-match", pattern, str(root)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    total = estimate_tokens("\n".join(lines))

    seen: list[str] = []
    for line in lines:
        path = line.split(":", 1)[0]
        if path not in seen:
            seen.append(path)
        if len(seen) >= read_files:
            break
    for path in seen:
        try:
            total += estimate_tokens(Path(path).read_text(errors="replace"))
        except OSError:
            continue
    return total


def _recall(rendered: str, expected: list[str]) -> float:
    if not expected:
        return 1.0
    hits = sum(1 for item in expected if item in rendered)
    return hits / len(expected)


def _search_pack(question: dict, repo: str, embedder, expand: bool):
    return run_search(
        question["question"], repo=repo, embedder=embedder, k=8,
        expand=expand, budget_tokens=1500,
    )


def _tool_pack(question: dict, repo: str):
    tool = question["tool"]
    target = question["target"]
    if tool == "symbol_context":
        return symbol_context(repo, target)
    if tool == "what_breaks":
        return what_breaks(repo, target)
    if tool == "what_tests":
        return what_tests(repo, target)
    if tool == "file_context":
        return file_context(repo, target)
    raise ValueError(f"unknown tool in golden set: {tool}")


def run(
    spec_path: Path, repo: str, root: Path, embedder, use_graph: bool = True
) -> list[Result]:
    spec = yaml.safe_load(spec_path.read_text())
    read_files = int(spec.get("baseline", {}).get("read_files", 4))
    results: list[Result] = []

    for question in spec["questions"]:
        result = Result(id=question["id"], question=question["question"])
        # A question may target a specific language sample; the grep baseline
        # has to be scoped to the same tree or the comparison is meaningless.
        q_repo = question.get("repo", repo)
        subtree = question.get("baseline_root")
        grep_root = (root / subtree) if subtree else root
        result.baseline_tokens = _grep_baseline(
            grep_root, question.get("baseline_grep", ""), read_files
        )

        if "tool" in question:
            pack = _tool_pack(question, q_repo)
            rendered = pack.render()
            result.coderag_tokens = pack.tokens()

            missing = [m for m in question.get("must_contain", []) if m not in rendered]
            over = (
                question.get("max_tokens")
                and result.coderag_tokens > question["max_tokens"]
            )
            result.recall = 1.0 - (len(missing) / max(1, len(question.get("must_contain", []))))
            result.passed = not missing and not over
            if missing:
                result.detail = "missing: " + ", ".join(missing)
            elif over:
                result.detail = f"over budget: {result.coderag_tokens} > {question['max_tokens']}"
        else:
            expected = question.get("expect_symbols", []) + question.get("expect_files", [])
            forbidden = question.get("forbid_symbols", [])
            pack = _search_pack(question, q_repo, embedder, expand=use_graph)
            rendered = pack.render()
            result.coderag_tokens = pack.tokens()
            result.recall = _recall(rendered, expected)

            leaked = [f for f in forbidden if f in rendered]
            result.passed = result.recall >= question.get("min_recall", 1.0) and not leaked
            if leaked:
                result.detail = "returned a forbidden match: " + ", ".join(leaked)
            elif not result.passed:
                result.detail = f"recall {result.recall:.2f} below {question.get('min_recall', 1.0)}"

        results.append(result)
    return results


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
