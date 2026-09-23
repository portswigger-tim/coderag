"""Derive TESTED_BY edges: which tests exercise which production code.

"What tests cover this?" is one of the most common questions before changing
something, and nothing else in the index answers it. Confidence is graded
rather than binary because the evidence genuinely varies in strength.
"""

from __future__ import annotations

from dataclasses import dataclass

from coderag.parsers.base import ParsedFile
from coderag.resolver import Resolver, symbol_id

HIGH, MEDIUM, LOW = "high", "medium", "low"


@dataclass(slots=True)
class TestEdge:
    target_id: str      # production symbol
    test_id: str        # test symbol
    confidence: str


def _strip_test_prefix(name: str) -> str:
    for prefix in ("test_", "Test", "test"):
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix) :].lstrip("_")
    for suffix in ("_test", "Test", "Tests", "Spec"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def derive(
    repo: str,
    parsed_files: dict[str, ParsedFile],
    test_paths: set[str],
    resolver: Resolver,
) -> list[TestEdge]:
    edges: dict[tuple[str, str], str] = {}

    for path in test_paths:
        parsed = parsed_files.get(path)
        if parsed is None:
            continue
        imported_names = set(resolver.imports_by_file.get(path, {}))

        for ref in parsed.references:
            if ref.via != "call":
                continue
            hit = resolver.resolve(path, ref.target_name)
            if hit is None:
                continue
            target_path, target_local = hit
            if target_path in test_paths:
                continue        # a test calling a helper in another test file

            confidence = HIGH if ref.target_name in imported_names else MEDIUM
            key = (
                symbol_id(repo, target_path, target_local),
                symbol_id(repo, path, ref.from_local_qname),
            )
            # Keep the strongest evidence if a test calls the same target twice.
            if key not in edges or confidence == HIGH:
                edges[key] = confidence

    # Naming convention, as a last resort: test_place_order -> place_order.
    # Only recorded where no call was observed, so it never downgrades real
    # evidence, and it is excluded from default output.
    for path in test_paths:
        parsed = parsed_files.get(path)
        if parsed is None:
            continue
        for sym in parsed.symbols:
            if sym.kind not in ("function", "method"):
                continue
            stem = _strip_test_prefix(sym.name)
            if not stem or stem == sym.name:
                continue
            hit = resolver.resolve(path, stem)
            if hit is None or hit[0] in test_paths:
                continue
            key = (
                symbol_id(repo, hit[0], hit[1]),
                symbol_id(repo, path, sym.local_qname),
            )
            edges.setdefault(key, LOW)

    return [
        TestEdge(target_id=t, test_id=s, confidence=c)
        for (t, s), c in edges.items()
    ]
