#!/usr/bin/env python
"""Replay sample/history.yaml into a throwaway git repo.

Co-change needs commits, and a real nested .git inside this project would be
awkward to ship. So the sample tree is copied to .cache/sample-repo and a
scripted history is replayed over it with fixed authors and dates, which
makes the resulting co-change edges deterministic and assertable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "samples"
SPEC = ROOT / "samples" / "history.yaml"
TARGET = ROOT / ".cache" / "sample-repo"


# Comment syntax per extension, used to stamp a revision marker so each
# scripted commit produces a real diff.
COMMENT = {
    ".py": "#", ".yaml": "#", ".yml": "#", ".toml": "#", ".cfg": "#", ".ini": "#",
    ".ts": "//", ".tsx": "//", ".js": "//", ".go": "//", ".java": "//", ".rs": "//",
    ".sql": "--",
}


def git(*args: str, cwd: Path, env: dict | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def write_revision(src: Path, dst: Path, revision: int) -> None:
    """Copy a file with a revision marker appended.

    Without a real content change git records an empty commit, and a commit
    with no diff contributes nothing to co-change. The marker is stripped
    again by the final cleanup commit, so the working tree ends up identical
    to samples/.
    """
    marker = COMMENT.get(src.suffix.lower())
    dst.parent.mkdir(parents=True, exist_ok=True)
    if marker is None:
        shutil.copy2(src, dst)
        return
    body = src.read_text(errors="replace").rstrip("\n")
    dst.write_text(f"{body}\n{marker} rev {revision}\n")


def main() -> int:
    if not SOURCE.exists():
        print(f"sample source missing: {SOURCE}", file=sys.stderr)
        return 1

    spec = yaml.safe_load(SPEC.read_text())
    author = spec["author"]
    start = date.fromisoformat(str(spec["start_date"]))

    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.mkdir(parents=True)

    git("init", "-q", "-b", "main", cwd=TARGET)
    # The user's global config may sign commits and run hooks. Neither can
    # succeed unattended, and neither belongs in a throwaway fixture.
    git("config", "commit.gpgsign", "false", cwd=TARGET)
    git("config", "tag.gpgsign", "false", cwd=TARGET)
    git("config", "core.hooksPath", "/dev/null", cwd=TARGET)
    git("config", "user.name", author.split("<")[0].strip(), cwd=TARGET)
    git("config", "user.email", author.split("<")[1].rstrip(">"), cwd=TARGET)

    for index, commit in enumerate(spec["commits"]):
        when = start + timedelta(days=index * 7)
        stamp = f"{when.isoformat()}T10:00:00+00:00"

        touched = []
        for rel in commit["files"]:
            src = SOURCE / rel
            if not src.exists():
                print(f"  warning: {rel} not in sample tree, skipping", file=sys.stderr)
                continue
            write_revision(src, TARGET / rel, index + 1)
            touched.append(rel)
        if not touched:
            continue

        git("add", *touched, cwd=TARGET)
        env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        subprocess.run(
            ["git", "commit", "-q", "--no-gpg-sign", "--no-verify",
             "-m", commit["message"], "--allow-empty"],
            cwd=TARGET, check=True, capture_output=True, env=env,
        )

    # Final commit: restore every file to its clean content and add anything
    # the script never named. This touches most of the tree at once, which is
    # exactly the kind of sweeping commit the co-change miner caps out -- so
    # it adds no spurious coupling.
    for src in SOURCE.rglob("*"):
        if src.is_file() and src.name != "history.yaml" and "__pycache__" not in src.parts:
            dst = TARGET / src.relative_to(SOURCE)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    final = start + timedelta(days=len(spec["commits"]) * 7)
    stamp = f"{final.isoformat()}T10:00:00+00:00"
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    git("add", "-A", cwd=TARGET)
    subprocess.run(
        ["git", "commit", "-q", "--no-gpg-sign", "--no-verify",
         "-m", "Strip revision markers", "--allow-empty"],
        cwd=TARGET, check=True, capture_output=True, env=env,
    )

    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=TARGET, capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"built {TARGET} with {count} commits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
