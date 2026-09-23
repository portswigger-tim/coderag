"""Symbol-aware chunking.

One chunk per function or method, prefixed with a context header. The header
is embedded but never displayed: it gives the embedding model the surrounding
facts (repo, file, class, signature) that a bare function body lacks, which is
what lets a natural-language query reach code that shares none of its words.
"""

from __future__ import annotations

from dataclasses import dataclass

from coderag.parsers.base import ParsedFile, Symbol

MAX_CHUNK_LINES = 120
OVERLAP_LINES = 15

# Import statements are pure vocabulary: they name every domain type in the
# file without saying anything about behaviour, which makes them match almost
# every query and answer none of them. They stay in the chunk *header* for
# context; they do not get to be a chunk of their own.
#
# Matching line prefixes alone only covers languages that put one import per
# line. Go, Rust and TypeScript all group them inside a delimiter:
#
#     import (                 use foo::{         import {
#         "context"                bar,               a,
#     )                        };                 } from "x"
#
# There only the opening line carries a keyword; every path inside is a bare
# token that no prefix matches, so the whole block used to survive into a
# module chunk. _strip_import_blocks removes the span between delimiters.
_IMPORT_PREFIXES = (
    "import ", "from ", "package ", "use ", "#include", "using ",
    "export * ", "export {", "require(", "const {",
)
# Only import grouping. Go's `var (` and `const (` blocks look identical but
# declare real values -- `const kvStreamPrefix = "KV_"` is an answer, not
# vocabulary -- so they stay.
_IMPORT_BLOCK_OPEN = ("import (", "import(", "import {", "use {")
# Below this, a module chunk is punctuation and closing braces.
MIN_MODULE_CHUNK_LINES = 3

# The licence header, and only the licence header.
#
# A repository puts a byte-identical Apache or MIT block at the top of every
# file. Indexed as content that is one near-duplicate vector per file -- 86
# of them across 7 distinct texts on one 161-file Go repo -- each competing
# in every search and answering nothing.
#
# The rule is positional, not syntactic: strip the run of comments *before
# any code*, which is where licences live in every language. Comments deeper
# in the file are left alone, because there they are documentation -- Rust's
# `///`, Go's `// Foo does...`, Java's `/** */` -- and a type's doc comment
# is often the only prose describing it.
_LINE_COMMENT_PREFIXES = ("#", "//", "--", ";", "!")
_BLOCK_COMMENT_SPANS = (("/*", "*/"), ("<!--", "-->"), ("=begin", "=end"))


def _is_import_line(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(prefix) for prefix in _IMPORT_PREFIXES)


def _strip_leading_comment_run(
    numbered: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Drop the comment run at the top of a file, stopping at the first code.

    Interior lines of a block comment carry no marker of their own --
    "Copyright 2025." is indistinguishable from code by prefix -- so block
    spans are tracked from their delimiters. Python's triple quote is
    deliberately not a delimiter here: it is also an ordinary string
    literal, and a module docstring is documentation worth keeping.
    """
    closer: str | None = None
    for index, (_, text) in enumerate(numbered):
        stripped = text.strip()
        if closer is not None:
            if closer in stripped:
                closer = None
            continue
        opened = next(
            (c for o, c in _BLOCK_COMMENT_SPANS if stripped.startswith(o)), None
        )
        if opened is not None:
            if opened not in stripped[2:]:   # not a one-line /* ... */
                closer = opened
            continue
        if any(stripped.startswith(p) for p in _LINE_COMMENT_PREFIXES):
            continue
        return numbered[index:]              # first real code line
    return []


def _strip_import_blocks(numbered: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop delimited import groups, keeping everything else.

    Tracks nesting depth from the opening line's own brackets so a one-line
    `use foo::{bar};` closes immediately and an unterminated block cannot
    swallow the rest of the file.
    """
    out: list[tuple[int, str]] = []
    depth = 0
    for lineno, text in numbered:
        stripped = text.strip()
        if depth == 0 and any(stripped.startswith(o) for o in _IMPORT_BLOCK_OPEN):
            depth = stripped.count("(") + stripped.count("{")
            depth -= stripped.count(")") + stripped.count("}")
            if depth < 0:
                depth = 0
            continue
        if depth > 0:
            depth += stripped.count("(") + stripped.count("{")
            depth -= stripped.count(")") + stripped.count("}")
            if depth < 0:
                depth = 0
            continue
        out.append((lineno, text))
    return out


def _is_comment_line(line: str) -> bool:
    """A Python-style comment line, stripped wherever it appears.

    Kept narrow on purpose. Extending this to `//` would also delete Rust's
    `///` and Go's doc comments from module-level chunks, and for a type
    that is frequently the only prose describing it. Licence headers are
    handled positionally instead, by _strip_leading_comment_run.
    """
    return line.strip().startswith("#")


@dataclass(slots=True)
class Chunk:
    text: str                 # header + body, what actually gets embedded
    start_line: int
    end_line: int
    symbol_qname: str | None   # file-local qname, resolved to full later
    kind: str


def _header(repo: str, parsed: ParsedFile, symbol: Symbol | None) -> str:
    # Deliberately no repo name: it is identical in every chunk of the index,
    # so it adds no discriminating signal and dilutes the parts that do.
    lines = [f"# file: {parsed.path}"]
    if parsed.module_docstring:
        lines.append(f"# module: {parsed.module_docstring.splitlines()[0][:120]}")
    if symbol is not None:
        if symbol.parent:
            lines.append(f"# class: {symbol.parent}")
        if symbol.signature:
            lines.append(f"# {symbol.signature}")
        if symbol.docstring:
            lines.append(f"# doc: {symbol.docstring.splitlines()[0][:160]}")
    return "\n".join(lines)


def _split_long(body: str, start_line: int) -> list[tuple[str, int, int]]:
    """Window an oversized function, with overlap so no boundary loses context."""
    lines = body.splitlines()
    if len(lines) <= MAX_CHUNK_LINES:
        return [(body, start_line, start_line + max(0, len(lines) - 1))]

    out: list[tuple[str, int, int]] = []
    step = MAX_CHUNK_LINES - OVERLAP_LINES
    for offset in range(0, len(lines), step):
        window = lines[offset : offset + MAX_CHUNK_LINES]
        if not window:
            break
        out.append(
            ("\n".join(window), start_line + offset, start_line + offset + len(window) - 1)
        )
        if offset + MAX_CHUNK_LINES >= len(lines):
            break
    return out


def chunk_file(repo: str, parsed: ParsedFile, source: str) -> list[Chunk]:
    """Chunk one parsed file: one chunk per callable, plus leftover module code."""
    chunks: list[Chunk] = []
    covered: set[int] = set()

    for symbol in parsed.symbols:
        if symbol.kind not in ("function", "method"):
            continue
        covered.update(range(symbol.start_line, symbol.end_line + 1))
        header = _header(repo, parsed, symbol)
        for body, start, end in _split_long(symbol.body, symbol.start_line):
            chunks.append(
                Chunk(
                    text=f"{header}\n{body}",
                    start_line=start,
                    end_line=end,
                    symbol_qname=symbol.local_qname,
                    kind=symbol.kind,
                )
            )

    # Whatever is left at module level -- imports, constants, top-level code --
    # still answers questions ("where is the client configured?"), so it is
    # chunked too rather than dropped.
    source_lines = source.splitlines()
    # Order matters: the block stripper has to see the opening `import (`
    # line to know a block has started, and _is_import_line would already
    # have removed it. So groups are stripped by span first, then the
    # per-line filters run over what survives.
    uncovered = [
        (i + 1, line)
        for i, line in enumerate(source_lines)
        if (i + 1) not in covered and line.strip()
    ]
    spans_removed = _strip_import_blocks(_strip_leading_comment_run(uncovered))
    leftover = [
        (lineno, line)
        for lineno, line in spans_removed
        if not _is_comment_line(line) and not _is_import_line(line)
    ]
    if leftover:
        header = _header(repo, parsed, None)
        block: list[tuple[int, str]] = []
        for lineno, text in leftover:
            if block and lineno - block[-1][0] > 3:
                if len(block) >= MIN_MODULE_CHUNK_LINES:
                    chunks.append(_module_chunk(header, block))
                block = []
            block.append((lineno, text))
            if len(block) >= MAX_CHUNK_LINES:
                chunks.append(_module_chunk(header, block))
                block = []
        if len(block) >= MIN_MODULE_CHUNK_LINES:
            chunks.append(_module_chunk(header, block))

    return chunks


def _module_chunk(header: str, block: list[tuple[int, str]]) -> Chunk:
    body = "\n".join(text for _, text in block)
    return Chunk(
        text=f"{header}\n{body}",
        start_line=block[0][0],
        end_line=block[-1][0],
        symbol_qname=None,
        kind="module",
    )
