"""Co-change mining: which files change together, from git history.

This finds coupling static analysis structurally cannot see -- a config file
and the code that reads it, a migration and its model, a build script and the
thing it builds. On a real 347-commit repo the strongest edges were between
files in different languages with no import or call between them.
"""

from __future__ import annotations

import itertools
import math
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# Co-change thresholds. All three guard against the same failure: a commit
# that touches everything implies coupling between nothing. A 400-file
# commit would emit ~80k spurious pairs, so sweeping commits are capped;
# support of 3 discards one-off coincidences; and the half-life decays
# evidence so a refactor from four years ago does not outvote last month.
MAX_FILES_PER_COMMIT = 25
MIN_SUPPORT = 3
HALF_LIFE_DAYS = 180.0


@dataclass(slots=True)
class CoChangeEdge:
    src: str            # lexicographically first, so each pair is stored once
    dst: str
    count: int
    last_seen: str      # ISO date
    weight: float       # recency-decayed support


def _run_git_log(root: Path, since_commit: str | None) -> str:
    rev_range = f"{since_commit}..HEAD" if since_commit else "HEAD"
    cmd = [
        "git", "-C", str(root), "log", rev_range,
        "--no-merges",              # merge commits re-report every change
        "-M",                       # follow renames, else history is severed
        "--name-only",
        "--pretty=format:%x00%H%x00%cI",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=300)
    if result.returncode != 0:
        return ""
    return result.stdout


def _parse_log(raw: str) -> list[tuple[str, datetime, list[str]]]:
    commits: list[tuple[str, datetime, list[str]]] = []
    current_sha: str | None = None
    current_when: datetime | None = None
    files: list[str] = []

    for line in raw.splitlines():
        if line.startswith("\x00"):
            if current_sha and files:
                commits.append((current_sha, current_when, files))
            parts = line.strip("\x00").split("\x00")
            current_sha = parts[0] if parts else None
            current_when = None
            if len(parts) > 1:
                try:
                    current_when = datetime.fromisoformat(parts[1])
                except ValueError:
                    current_when = None
            files = []
        elif line.strip():
            files.append(line.strip())

    if current_sha and files:
        commits.append((current_sha, current_when, files))
    return commits


def mine(
    root: Path,
    tracked_paths: set[str],
    since_commit: str | None = None,
    git_root: Path | None = None,
) -> list[CoChangeEdge]:
    """Build co-change edges, keyed by path relative to the indexed root.

    `git_root` is the enclosing working tree, which is above `root` whenever
    a subdirectory is being indexed. History is read there and paths are
    translated back, so indexing `repo/services/payments` still gets the
    coupling that lives in `repo`'s history.
    """
    work_tree = git_root or root
    try:
        prefix = root.resolve().relative_to(work_tree.resolve()).as_posix()
    except ValueError:
        prefix = ""
    prefix = "" if prefix in ("", ".") else prefix + "/"

    raw = _run_git_log(work_tree, since_commit)
    if not raw.strip():
        return []

    now = datetime.now(timezone.utc)
    pair_count: dict[tuple[str, str], int] = defaultdict(int)
    pair_weight: dict[tuple[str, str], float] = defaultdict(float)
    pair_last: dict[tuple[str, str], str] = {}

    for _sha, when, files in _parse_log(raw):
        relevant = sorted({
            rel for rel in (
                f[len(prefix):] if prefix and f.startswith(prefix) else
                (f if not prefix else None)
                for f in files
            )
            if rel is not None and rel in tracked_paths
        })
        # A sweeping commit touching hundreds of files is a rename, a reformat
        # or a licence header -- it says nothing about coupling, and left
        # uncapped it would emit tens of thousands of spurious pairs.
        if len(relevant) < 2 or len(relevant) > MAX_FILES_PER_COMMIT:
            continue

        if when is None:
            decay = 0.5
            stamp = ""
        else:
            age_days = max(0.0, (now - when).total_seconds() / 86400.0)
            decay = math.exp(-age_days / HALF_LIFE_DAYS)
            stamp = when.date().isoformat()

        for a, b in itertools.combinations(relevant, 2):
            key = (a, b)
            pair_count[key] += 1
            pair_weight[key] += decay
            if stamp and stamp > pair_last.get(key, ""):
                pair_last[key] = stamp

    return [
        CoChangeEdge(
            src=a, dst=b, count=count,
            last_seen=pair_last.get((a, b), ""),
            weight=round(pair_weight[(a, b)], 4),
        )
        for (a, b), count in pair_count.items()
        if count >= MIN_SUPPORT
    ]
