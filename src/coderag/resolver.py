"""Repo-wide name resolution.

Tree-sitter gives us references by name only. This pass binds them to actual
symbols, scoped by imports. It is a heuristic, not a compiler: ambiguity is
recorded as `resolved: false` rather than guessed at, and the unresolved ratio
is reported so retrieval quality is measurable instead of assumed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from coderag.parsers.base import ParsedFile


@dataclass(slots=True)
class ResolvedEdge:
    src_id: str              # symbol id of the referencing symbol
    dst_id: str              # symbol id of the referenced symbol
    via: str
    resolved: bool


def symbol_id(repo: str, path: str, local_qname: str) -> str:
    return f"{repo}:{path}:{local_qname}"


def qualified_name(repo: str, path: str, local_qname: str) -> str:
    """Dotted name used in tool arguments, e.g. services.pricing.Foo.bar.

    Where the file is named after the type it declares -- Java's one-class-
    per-file rule, and the same convention elsewhere -- the name would
    otherwise repeat: shop.PricingService.PricingService.apply. The
    duplicate segment is collapsed, because these names are the tool's
    addressing scheme and have to be typeable.
    """
    module = path.rsplit(".", 1)[0].replace("/", ".")
    head = local_qname.split(".", 1)[0]
    if module.endswith(f".{head}"):
        module = module[: -(len(head) + 1)]
    return f"{module}.{local_qname}" if module else local_qname


class Resolver:
    """Builds the name -> symbol index once, then answers per-reference."""

    def __init__(self, repo: str, parsed_files: dict[str, ParsedFile]) -> None:
        self.repo = repo
        self.parsed = parsed_files

        # (lang, name) -> list of (path, local_qname). Keying on language
        # matters in a polyglot repo: PricingService exists in the Python,
        # TypeScript, Java and Rust samples, and binding a Python call to a
        # Rust definition would be confidently wrong.
        self.by_name: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        self.lang_by_path: dict[str, str] = {}
        # path -> {imported name -> source module path-ish}
        self.imports_by_file: dict[str, dict[str, str]] = {}
        # module-ish path (dotted, no extension) -> file path
        self.module_to_path: dict[str, str] = {}

        for path, pf in parsed_files.items():
            module = path.rsplit(".", 1)[0].replace("/", ".")
            self.module_to_path[module] = path
            self.module_to_path[module.rsplit(".", 1)[-1]] = path
            self.lang_by_path[path] = pf.lang
            for sym in pf.symbols:
                self.by_name[(pf.lang, sym.name)].append((path, sym.local_qname))
            table: dict[str, str] = {}
            for imp in pf.imports:
                for name in imp.names:
                    table[name] = imp.module
                if imp.alias:
                    table[imp.alias] = imp.module
                table.setdefault(imp.module.rsplit(".", 1)[-1], imp.module)
            self.imports_by_file[path] = table

    def _candidates(self, from_path: str, name: str) -> list[tuple[str, str]]:
        lang = self.lang_by_path.get(from_path)
        if lang is None:
            return []
        return self.by_name.get((lang, name), [])

    def resolve(self, from_path: str, target_name: str) -> tuple[str, str] | None:
        """Return (path, local_qname) for a referenced name, or None.

        Order matters and mirrors how a reader would resolve it: something
        defined right here, then something this file imported, then something
        in the same package, then a repo-unique name.
        """
        candidates = self._candidates(from_path, target_name)
        if not candidates:
            return None

        # 1. Defined in the same file.
        local = [c for c in candidates if c[0] == from_path]
        if len(local) == 1:
            return local[0]
        if local:
            # Several same-named symbols in one file (overloads, nested defs):
            # prefer the top-level one.
            local.sort(key=lambda c: c[1].count("."))
            return local[0]

        # 2. Explicitly imported by this file.
        imports = self.imports_by_file.get(from_path, {})
        if target_name in imports:
            module = imports[target_name]
            target_path = self._module_path(module)
            if target_path:
                hit = [c for c in candidates if c[0] == target_path]
                if len(hit) == 1:
                    return hit[0]

        # 3. Same package (sibling directory).
        package = from_path.rsplit("/", 1)[0] if "/" in from_path else ""
        siblings = [c for c in candidates if c[0].rsplit("/", 1)[0] == package]
        if len(siblings) == 1:
            return siblings[0]

        # 4. Unique across the whole repo.
        if len(candidates) == 1:
            return candidates[0]

        return None   # genuinely ambiguous -- recorded, not guessed

    def _module_path(self, module: str) -> str | None:
        module = module.lstrip(".")
        if module in self.module_to_path:
            return self.module_to_path[module]
        tail = module.rsplit(".", 1)[-1]
        return self.module_to_path.get(tail)

    def resolve_all(self) -> tuple[list[ResolvedEdge], dict[str, int]]:
        """Bind every reference in the repo. Returns edges and a stats dict."""
        edges: list[ResolvedEdge] = []
        stats = {"total": 0, "resolved": 0, "unresolved": 0, "external": 0}

        for path, pf in self.parsed.items():
            for ref in pf.references:
                stats["total"] += 1
                hit = self.resolve(path, ref.target_name)
                if hit is None:
                    # Overwhelmingly stdlib/third-party calls. Counted, not stored:
                    # an edge to a node we do not have is not useful context.
                    known = bool(self._candidates(path, ref.target_name))
                    stats["unresolved" if known else "external"] += 1
                    continue
                stats["resolved"] += 1
                dst_path, dst_local = hit
                edges.append(
                    ResolvedEdge(
                        src_id=symbol_id(self.repo, path, ref.from_local_qname),
                        dst_id=symbol_id(self.repo, dst_path, dst_local),
                        via=ref.via,
                        resolved=True,
                    )
                )
        return edges, stats
