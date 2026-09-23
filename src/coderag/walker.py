"""File discovery: what to index, what to ignore, and what changed."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pathspec

from coderag.config import DEFAULT_IGNORE_DIRS, DEFAULT_IGNORE_GLOBS
from coderag.parsers.treesitter import language_for_path

# Anything larger is generated, vendored or minified in practice, and
# embedding it costs more than the answer it could ever give.
MAX_FILE_BYTES = 1_000_000

# Config and data files carry no symbols but plenty of answers: an agent
# changing a feature usually has to change its configuration too, and that
# coupling is invisible unless these files are in the graph.
DATA_EXTENSIONS: dict[str, str] = {
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".json": "json",
    ".ini": "ini", ".cfg": "ini", ".conf": "ini", ".env": "ini",
    ".sql": "sql", ".properties": "ini",
}


def data_language_for_path(path) -> str | None:
    from pathlib import Path as _P
    return DATA_EXTENSIONS.get(_P(path).suffix.lower())

# Path fragments that mark a file as test code. Test symbols stay searchable
# but are down-weighted, so implementation is not crowded out by its tests.
_TEST_MARKERS = (
    "/tests/", "/test/", "/__tests__/", "/spec/",
    "src/test/java/", "/testing/",
)
_TEST_NAME_PATTERNS = (
    "test_", "_test.", ".test.", ".spec.", "Test.java", "Tests.java", "_spec.",
)


@dataclass(slots=True)
class DiscoveredFile:
    path: str          # repo-relative, posix separators
    abs_path: Path
    lang: str
    sha256: str
    size: int
    is_test: bool
    is_data: bool = False       # config/data: chunked and searchable, not parsed


def is_test_path(rel_path: str) -> bool:
    lowered = "/" + rel_path.lower()
    if any(marker in lowered for marker in _TEST_MARKERS):
        return True
    name = Path(rel_path).name
    return any(pat.lower() in name.lower() for pat in _TEST_NAME_PATTERNS)


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    patterns: list[str] = []
    gitignore = root / ".gitignore"
    if gitignore.exists():
        patterns.extend(gitignore.read_text(errors="replace").splitlines())
    if not patterns:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(131072), b""):
            digest.update(block)
    return digest.hexdigest()


def discover(root: Path, only: str | None = None) -> list[DiscoveredFile]:
    """Walk a tree and return every indexable source file.

    `only` restricts to a subtree, which is how a first pass on an unfamiliar
    monolith stays affordable.
    """
    root = root.resolve()
    spec = _load_gitignore(root)
    glob_spec = pathspec.PathSpec.from_lines("gitwildmatch", DEFAULT_IGNORE_GLOBS)
    scope = (root / only).resolve() if only else root

    found: list[DiscoveredFile] = []
    for dirpath, dirnames, filenames in os.walk(scope):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS]
        current = Path(dirpath)
        for filename in filenames:
            abs_path = current / filename
            try:
                rel = abs_path.relative_to(root).as_posix()
            except ValueError:
                continue

            lang = language_for_path(abs_path)
            is_data = False
            if lang is None:
                lang = data_language_for_path(abs_path)
                is_data = lang is not None
            if lang is None:
                continue
            if glob_spec.match_file(rel) or (spec and spec.match_file(rel)):
                continue
            try:
                size = abs_path.stat().st_size
            except OSError:
                continue
            if size == 0 or size > MAX_FILE_BYTES:
                continue

            found.append(
                DiscoveredFile(
                    path=rel,
                    abs_path=abs_path,
                    lang=lang,
                    sha256=sha256_of(abs_path),
                    size=size,
                    is_test=is_test_path(rel),
                    is_data=is_data,
                )
            )

    found.sort(key=lambda f: f.path)
    return found


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_root(path: Path) -> Path | None:
    """The enclosing git working tree, which may be above the indexed path.

    Indexing a subdirectory is ordinary usage; looking for .git only in the
    indexed directory would silently drop co-change for every such run.
    """
    top = _git(path, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def git_head(root: Path) -> str | None:
    """Current commit, or None when this is not a git working tree."""
    return _git(root, "rev-parse", "HEAD") or None


def has_git_history(root: Path) -> bool:
    """False for shallow clones and non-repos, where co-change is unavailable."""
    top = git_root(root)
    if top is None:
        return False
    if (top / ".git" / "shallow").exists():
        return False
    return git_head(top) is not None
