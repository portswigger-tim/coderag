"""Name resolution, test linking and co-change mining, all database-free."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coderag import testlink
from coderag.gitmine import mine
from coderag.parsers.treesitter import parse_source
from coderag.resolver import Resolver, qualified_name


def _parse(files: dict[str, tuple[bytes, str]]):
    return {path: parse_source(path, src, lang) for path, (src, lang) in files.items()}


def test_resolution_prefers_the_same_file_then_imports():
    files = _parse({
        "services/pricing.py": (b"def helper():\n    pass\n\ndef apply():\n    return helper()\n", "python"),
        "other/helper.py": (b"def helper():\n    pass\n", "python"),
    })
    resolver = Resolver("r", files)
    assert resolver.resolve("services/pricing.py", "helper")[0] == "services/pricing.py"


def test_resolution_never_crosses_a_language_boundary():
    """PricingService exists in four sample languages; binding across them
    would be confidently wrong."""
    files = _parse({
        "py/pricing.py": (b"class PricingService:\n    pass\n", "python"),
        "ts/pricing.ts": (b"export class PricingService {}\nexport function go(): void { new PricingService(); }\n", "typescript"),
    })
    resolver = Resolver("r", files)
    hit = resolver.resolve("ts/pricing.ts", "PricingService")
    assert hit is not None and hit[0] == "ts/pricing.ts"
    assert resolver.resolve("py/pricing.py", "nonexistent") is None


def test_ambiguity_is_reported_not_guessed():
    files = _parse({
        "a/x.py": (b"def shared():\n    pass\n", "python"),
        "b/y.py": (b"def shared():\n    pass\n", "python"),
        "c/z.py": (b"def call_it():\n    return shared()\n", "python"),
    })
    resolver = Resolver("r", files)
    assert resolver.resolve("c/z.py", "shared") is None
    _edges, stats = resolver.resolve_all()
    assert stats["unresolved"] >= 1


def test_qualified_name_collapses_a_duplicated_class_segment():
    assert qualified_name("r", "shop/PricingService.java", "PricingService.apply") \
        == "shop.PricingService.apply"
    assert qualified_name("r", "services/pricing.py", "PricingService.apply") \
        == "services.pricing.PricingService.apply"


def test_test_links_are_graded_by_evidence():
    files = _parse({
        "services/pricing.py": (b"def apply_discount():\n    return 1\n", "python"),
        "tests/test_pricing.py": (
            b"from services.pricing import apply_discount\n\n"
            b"def test_apply_discount():\n    assert apply_discount() == 1\n", "python"),
    })
    resolver = Resolver("r", files)
    edges = testlink.derive("r", files, {"tests/test_pricing.py"}, resolver)
    assert edges and edges[0].confidence == "high"   # imported and called


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    for i in range(4):
        (tmp_path / "a.py").write_text(f"x = {i}\n")
        (tmp_path / "b.yaml").write_text(f"y: {i}\n")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "--no-gpg-sign", "--no-verify", "-m", f"c{i}")
    return tmp_path


def test_cochange_finds_coupling_with_no_code_link(tiny_repo: Path):
    edges = mine(tiny_repo, {"a.py", "b.yaml"})
    assert len(edges) == 1
    assert {edges[0].src, edges[0].dst} == {"a.py", "b.yaml"}
    assert edges[0].count == 4


def test_cochange_is_empty_without_history(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert mine(tmp_path, {"a.py"}) == []


def test_bulk_commits_do_not_explode_into_spurious_pairs(tiny_repo: Path):
    """A sweeping commit says nothing about coupling and must be capped out."""
    from coderag.gitmine import MAX_FILES_PER_COMMIT
    names = [f"f{i}.py" for i in range(MAX_FILES_PER_COMMIT + 5)]
    for name in names:
        (tiny_repo / name).write_text("z = 1\n")
    _git(tiny_repo, "add", "-A")
    _git(tiny_repo, "commit", "-q", "--no-gpg-sign", "--no-verify", "-m", "sweep")
    edges = mine(tiny_repo, set(names) | {"a.py", "b.yaml"})
    assert all({e.src, e.dst} == {"a.py", "b.yaml"} for e in edges)
