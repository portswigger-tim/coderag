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
_IMPORT_PREFIXES = (
    "import ", "from ", "package ", "use ", "#include", "using ",
    "export * ", "export {", "require(", "const {",
)
# Below this, a module chunk is punctuation and closing braces.
MIN_MODULE_CHUNK_LINES = 3


def _is_import_line(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(prefix) for prefix in _IMPORT_PREFIXES)


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
    leftover = [
        (i + 1, line)
        for i, line in enumerate(source_lines)
        if (i + 1) not in covered
        and line.strip()
        and not line.strip().startswith("#")
        and not _is_import_line(line)
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
