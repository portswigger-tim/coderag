"""Generic tree-sitter extraction driven by per-language .scm query files.

Adding a language means adding `queries/<lang>.scm` plus an entry in
LANGUAGE_BY_EXT and LANG_PROFILE -- no changes to the logic below.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import tree_sitter as ts
import tree_sitter_language_pack as tslp

from coderag.parsers.base import Import, ParsedFile, Reference, Symbol

QUERY_DIR = Path(__file__).parent / "queries"

LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
}

# Languages whose .scm can express type annotations. Anything absent here has
# its ParsedFile flagged types_unavailable, so a context pack can admit the
# USES list is partial rather than implying completeness.
TYPED_LANGUAGES: frozenset[str] = frozenset(
    {"python", "typescript", "tsx", "go", "java", "rust"}
)

_KIND_BY_CAPTURE = {
    "def.function": "function",
    "def.class": "class",
    "def.const": "const",
    "def.interface": "interface",
    "def.struct": "struct",
    "def.enum": "enum",
}

_WS = re.compile(r"\s+")


class UnsupportedLanguage(Exception):
    pass


@functools.lru_cache(maxsize=32)
def _query_for(lang: str) -> ts.Query:
    path = QUERY_DIR / f"{lang}.scm"
    if not path.exists():
        raise UnsupportedLanguage(lang)
    return ts.Query(tslp.get_language(lang), path.read_text())


@functools.lru_cache(maxsize=32)
def _parser_for(lang: str):
    return tslp.get_parser(lang)


def language_for_path(path: str | Path) -> str | None:
    return LANGUAGE_BY_EXT.get(Path(path).suffix.lower())


def _line(node: ts.Node) -> int:
    return node.start_point[0] + 1


def _text(node: ts.Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _signature(def_node: ts.Node, body_node: ts.Node | None, src: bytes) -> str:
    """The header of a definition: everything before its body."""
    end = body_node.start_byte if body_node is not None else def_node.end_byte
    raw = src[def_node.start_byte : end].decode("utf-8", "replace")
    return _WS.sub(" ", raw).strip().rstrip("{").strip()


def _string_literal_text(node: ts.Node, src: bytes) -> str | None:
    """Clean text of a string node, tolerating both grammar shapes.

    Recent tree-sitter-python emits a bare `string` for a docstring; older
    versions wrap it in an `expression_statement`. Accept either.
    """
    if node.type == "expression_statement" and node.named_child_count == 1:
        node = node.named_children[0]
    if node.type != "string":
        return None
    for child in node.named_children:
        if child.type == "string_content":
            return _text(child, src).strip()
    return _text(node, src).strip("\"'").strip()


def _python_docstring(body_node: ts.Node, src: bytes) -> str:
    if body_node.named_child_count == 0:
        return ""
    return _string_literal_text(body_node.named_children[0], src) or ""


def _innermost_owner(symbols: list[Symbol], offset: int) -> Symbol | None:
    """The tightest-enclosing symbol for a byte offset.

    Narrowest containing span wins, which is exact even when several
    definitions share a line.
    """
    owner = None
    for sym in symbols:
        if sym.start_byte <= offset < sym.end_byte:
            if owner is None or (sym.end_byte - sym.start_byte) < (
                owner.end_byte - owner.start_byte
            ):
                owner = sym
    return owner


def parse_source(path: str, src: bytes, lang: str) -> ParsedFile:
    """Extract definitions, references and imports from one file."""
    query = _query_for(lang)
    tree = _parser_for(lang).parse(src)
    matches = ts.QueryCursor(query).matches(tree.root_node)

    parsed = ParsedFile(
        path=path,
        lang=lang,
        loc=src.count(b"\n") + 1,
        types_unavailable=lang not in TYPED_LANGUAGES,
    )

    # Pass A: definitions. Collected first so references can be attributed to
    # their enclosing symbol by line containment.
    pending_refs: list[tuple[str, str, int, int]] = []   # (target, via, line, byte)
    imports: list[Import] = []

    for _pattern, caps in matches:
        def_capture = next((c for c in caps if c in _KIND_BY_CAPTURE), None)
        if def_capture:
            node = caps[def_capture][0]
            name_nodes = caps.get("def.name")
            if not name_nodes:
                continue
            name = _text(name_nodes[0], src)
            kind = _KIND_BY_CAPTURE[def_capture]

            # tree-sitter cannot express "screaming snake case", so the
            # module-constant rule is applied here.
            if kind == "const" and not (name.isupper() and len(name) > 1):
                continue

            body_nodes = caps.get("def.body")
            body = body_nodes[0] if body_nodes else None
            doc = (
                _python_docstring(body, src)
                if lang == "python" and kind in ("function", "class") and body
                else ""
            )
            parsed.symbols.append(
                Symbol(
                    name=name,
                    kind=kind,
                    start_line=_line(node),
                    end_line=node.end_point[0] + 1,
                    signature=_signature(node, body, src),
                    docstring=doc[:400],
                    body=_text(node, src),
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                )
            )
            continue

        for capture, nodes in caps.items():
            if capture.startswith("ref."):
                via = capture.split(".", 1)[1].removesuffix(".str")
                for n in nodes:
                    target = _text(n, src).strip("\"'")
                    if target:
                        pending_refs.append((target, via, _line(n), n.start_byte))
            elif capture == "import.module":
                names = [_text(x, src) for x in caps.get("import.name", [])]
                alias_nodes = caps.get("import.alias")
                imports.append(
                    Import(
                        # Go and Rust write the path as a quoted literal.
                        module=_text(nodes[0], src).strip("\"'"),
                        names=names,
                        alias=_text(alias_nodes[0], src) if alias_nodes else None,
                        line=_line(nodes[0]),
                    )
                )

    parsed.imports = imports

    # Methods: a function whose tightest container is a class.
    classes = [s for s in parsed.symbols if s.kind in ("class", "interface", "struct")]
    for sym in parsed.symbols:
        if sym.kind != "function":
            continue
        for cls in classes:
            if cls is sym:
                continue
            if cls.start_line <= sym.start_line and sym.end_line <= cls.end_line:
                if sym.parent is None or len(cls.name) > 0:
                    sym.parent = cls.name
                    sym.kind = "method"

    # Pass B: attribute references to their enclosing definition.
    for target, via, line, offset in pending_refs:
        owner = _innermost_owner(parsed.symbols, offset)
        if owner is None:
            continue
        if owner.name == target:
            continue   # self-reference, e.g. recursion or the def's own name
        parsed.references.append(
            Reference(
                from_local_qname=owner.local_qname,
                target_name=target,
                via=via,
                line=line,
                byte=offset,
            )
        )

    if lang == "python":
        parsed.module_docstring = _module_docstring(tree.root_node, src)

    return parsed


def _module_docstring(root: ts.Node, src: bytes) -> str:
    if root.named_child_count == 0:
        return ""
    return (_string_literal_text(root.named_children[0], src) or "")[:400]
