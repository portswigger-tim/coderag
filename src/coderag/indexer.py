"""Indexing orchestration: walk, parse, chunk, embed, write, resolve.

Resumability comes from ordering rather than a separate work queue: a file's
symbols and chunks are written *before* its content hash is recorded, so a
crash mid-run leaves that file marked incomplete and it is reprocessed on the
next run. Nothing is ever half-recorded as done.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from coderag import db
from coderag.chunker import chunk_file
from coderag.embedder import Embedder, get_embedder
from coderag.parsers.base import ParsedFile
from coderag.parsers.treesitter import UnsupportedLanguage, parse_source
from coderag.resolver import Resolver, qualified_name, symbol_id
from coderag import gitmine, testlink
from coderag.walker import (
    DiscoveredFile, discover, git_head, git_root, has_git_history,
)

PENDING = "__indexing__"

SYMBOL_WRITE = """
UNWIND $rows AS row
MERGE (s:Symbol {id: row.id})
SET s.repo = row.repo, s.path = row.path, s.name = row.name,
    s.qname = row.qname, s.local_qname = row.local_qname,
    s.kind = row.kind, s.start_line = row.start_line,
    s.end_line = row.end_line, s.signature = row.signature,
    s.docstring = row.docstring, s.parent = row.parent,
    s.is_test = row.is_test
WITH s, row
MATCH (f:File {uid: row.repo + ':' + row.path})
MERGE (f)-[:DEFINES]->(s)
"""

NESTED_WRITE = """
UNWIND $rows AS row
MATCH (p:Symbol {id: row.parent_id}), (c:Symbol {id: row.child_id})
MERGE (p)-[:DEFINES]->(c)
"""

CHUNK_WRITE = """
UNWIND $rows AS row
MERGE (c:Chunk {id: row.id})
SET c.repo = row.repo, c.path = row.path, c.text = row.text,
    c.start_line = row.start_line, c.end_line = row.end_line,
    c.symbol_qname = row.symbol_qname, c.kind = row.kind,
    c.is_test = row.is_test, c.embedding = row.embedding
WITH c, row
MATCH (f:File {uid: row.repo + ':' + row.path})
MERGE (c)-[:PART_OF]->(f)
WITH c, row WHERE row.symbol_qname IS NOT NULL
MATCH (s:Symbol {qname: row.symbol_qname, repo: row.repo})
MERGE (c)-[:DESCRIBES]->(s)
"""


@dataclass
class IndexStats:
    repo: str = ""
    files_total: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    files_pruned: int = 0
    symbols: int = 0
    chunks: int = 0
    edges: int = 0
    test_edges: int = 0
    cochange_edges: int = 0
    resolution: dict[str, int] = field(default_factory=dict)
    has_history: bool = False

    @property
    def unresolved_ratio(self) -> float:
        internal = self.resolution.get("resolved", 0) + self.resolution.get("unresolved", 0)
        if internal == 0:
            return 0.0
        return self.resolution.get("unresolved", 0) / internal


def _parse_one(args: tuple[str, str, str]) -> tuple[str, ParsedFile | None, str]:
    """Worker body for the parse pool. Returns (path, parsed, source_text)."""
    path, abs_path, lang = args
    try:
        raw = Path(abs_path).read_bytes()
        parsed = parse_source(path, raw, lang)
        return path, parsed, raw.decode("utf-8", "replace")
    except (UnsupportedLanguage, OSError, ValueError):
        return path, None, ""


def _existing_hashes(repo: str) -> dict[str, str]:
    rows = db.read(
        "MATCH (f:File {repo: $repo}) RETURN f.path AS path, f.sha256 AS sha",
        repo=repo,
    )
    return {r["path"]: r["sha"] for r in rows}


def _delete_file_subgraph(repo: str, paths: list[str]) -> None:
    if not paths:
        return
    db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (f:File {repo: row.repo, path: row.path})
        OPTIONAL MATCH (f)-[:DEFINES]->(s:Symbol)
        OPTIONAL MATCH (f)<-[:PART_OF]-(c:Chunk)
        DETACH DELETE s, c
        """,
        [{"repo": repo, "path": p} for p in paths],
    )


def index_repo(
    root: Path,
    repo: str | None = None,
    only: str | None = None,
    force: bool = False,
    embedder: Embedder | None = None,
    progress=None,
) -> IndexStats:
    """Index a source tree.

    There is no option to drop the vector index for the load. It was tried:
    measured against 139,535 vectors already indexed -- past the point it
    was supposed to help -- deferring came out *slower* in both runs (156s
    and 165s against 148s and 153s), because rebuilding the whole index at
    the end costs more than maintaining it per insert. Writes are only ~4%
    of a load anyway; embedding is the rest. It also made vector search
    unavailable for every repo while it ran, so it was a footgun that lost
    its own race.
    """
    root = root.resolve()
    repo = repo or root.name
    embedder = embedder or get_embedder()
    stats = IndexStats(repo=repo, has_history=has_git_history(root))
    return _index(root, repo, only, force, embedder, progress, stats)


def _index(root, repo, only, force, embedder, progress, stats) -> IndexStats:
    files = discover(root, only=only)
    stats.files_total = len(files)

    # Always read what is already indexed: --force changes whether we *skip*
    # unchanged files, not whether we prune files that have gone away.
    indexed = _existing_hashes(repo)
    previous = {} if force else indexed
    changed: list[DiscoveredFile] = [
        f for f in files if previous.get(f.path) != f.sha256
    ]
    stats.files_skipped = len(files) - len(changed)

    # Files indexed previously but gone from disk.
    on_disk = {f.path for f in files}
    stale_paths = [p for p in indexed if p not in on_disk]
    if stale_paths and only is None:
        _delete_file_subgraph(repo, stale_paths)
        db.write_batched(
            "UNWIND $rows AS row MATCH (f:File {repo: row.repo, path: row.path}) DETACH DELETE f",
            [{"repo": repo, "path": p} for p in stale_paths],
        )
        stats.files_pruned = len(stale_paths)

    db.write_batched(
        """
        UNWIND $rows AS row
        MERGE (r:Repo {name: row.name})
        SET r.root = row.root, r.embedder = row.embedder, r.dim = row.dim,
            r.commit = row.commit, r.has_history = row.has_history,
            r.indexed_at = datetime()
        """,
        [{
            "name": repo, "root": str(root), "embedder": embedder.name,
            "dim": embedder.dim, "commit": git_head(git_root(root) or root),
            "has_history": stats.has_history,
        }],
    )

    if not changed:
        stats.resolution = _reparse_for_stats_only(repo)
        if stats.has_history:
            stats.cochange_edges = _write_cochange(repo, root, {f.path for f in files})
        return stats

    _delete_file_subgraph(repo, [f.path for f in changed])

    # Mark every changed file as in-flight. A crash leaves the marker, which
    # forces a reindex of exactly those files next run.
    db.write_batched(
        """
        UNWIND $rows AS row
        MERGE (f:File {uid: row.uid})
        SET f.repo = row.repo, f.path = row.path, f.lang = row.lang,
            f.is_test = row.is_test, f.sha256 = row.pending
        WITH f, row
        MATCH (r:Repo {name: row.repo})
        MERGE (r)-[:CONTAINS]->(f)
        """,
        [{
            "uid": f"{repo}:{f.path}", "repo": repo, "path": f.path,
            "lang": f.lang, "is_test": f.is_test, "pending": PENDING,
        } for f in changed],
        batch_size=db.WRITE_BATCH_SIZE,
    )

    # --- parse (process pool: CPU-bound and independent per file) ----------
    parsed_files: dict[str, ParsedFile] = {}
    sources: dict[str, str] = {}
    work = [(f.path, str(f.abs_path), f.lang) for f in changed if not f.is_data]
    max_workers = min(8, (len(work) // 8) + 1)

    if len(work) > 16 and max_workers > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = pool.map(_parse_one, work, chunksize=8)
            for path, parsed, source in results:
                if parsed is not None:
                    parsed_files[path] = parsed
                    sources[path] = source
                if progress:
                    progress("parse", 1)
    else:
        for item in work:
            path, parsed, source = _parse_one(item)
            if parsed is not None:
                parsed_files[path] = parsed
                sources[path] = source
            if progress:
                progress("parse", 1)

    test_paths = {f.path for f in changed if f.is_test}

    # --- symbols and chunks, in groups -----------------------------------
    #
    # Grouped to bound memory. A million-line repo produces tens of
    # thousands of chunks, and holding every chunk body plus its embedding
    # vector in one list before writing would cost well over a gigabyte for
    # no benefit. Each group is embedded and written before the next is
    # built, so peak memory is set by the group size, not the repo size.
    test_paths = {f.path for f in changed if f.is_test}
    group_size = max(db.WRITE_BATCH_SIZE // 4, 25)

    for offset in range(0, len(changed), group_size):
        group = changed[offset : offset + group_size]
        group_paths = [f.path for f in group if f.path in parsed_files]

        symbol_rows = []
        for path in group_paths:
            for sym in parsed_files[path].symbols:
                symbol_rows.append({
                    "id": symbol_id(repo, path, sym.local_qname),
                    "repo": repo, "path": path, "name": sym.name,
                    "qname": qualified_name(repo, path, sym.local_qname),
                    "local_qname": sym.local_qname,
                    "kind": sym.kind, "start_line": sym.start_line,
                    "end_line": sym.end_line, "signature": sym.signature,
                    "docstring": sym.docstring, "parent": sym.parent,
                    "is_test": path in test_paths,
                })
        stats.symbols += db.write_batched(SYMBOL_WRITE, symbol_rows)

        nested = [
            {"parent_id": symbol_id(repo, path, sym.parent),
             "child_id": symbol_id(repo, path, sym.local_qname)}
            for path in group_paths
            for sym in parsed_files[path].symbols
            if sym.parent
        ]
        db.write_batched(NESTED_WRITE, nested)

        chunk_rows: list[dict] = []
        for path in group_paths:
            for i, chunk in enumerate(chunk_file(repo, parsed_files[path], sources[path])):
                chunk_rows.append({
                    "id": f"{repo}:{path}:{i}",
                    "repo": repo, "path": path, "text": chunk.text,
                    "start_line": chunk.start_line, "end_line": chunk.end_line,
                    "symbol_qname": (
                        qualified_name(repo, path, chunk.symbol_qname)
                        if chunk.symbol_qname else None
                    ),
                    "kind": chunk.kind, "is_test": path in test_paths,
                })

        # Config and data files carry no symbols but plenty of answers: an
        # agent changing a feature usually has to change its configuration
        # too, and that coupling is invisible unless these are indexed.
        for df in (f for f in group if f.is_data):
            try:
                text = df.abs_path.read_text(errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            window = 60
            for start_line in range(0, max(1, len(lines)), window):
                block = lines[start_line : start_line + window]
                if not any(ln.strip() for ln in block):
                    continue
                chunk_rows.append({
                    "id": f"{repo}:{df.path}:{start_line // window}",
                    "repo": repo, "path": df.path,
                    "text": f"# file: {df.path} | config\n" + "\n".join(block),
                    "start_line": start_line + 1,
                    "end_line": start_line + len(block),
                    "symbol_qname": None, "kind": "config",
                    "is_test": df.is_test,
                })

        # The whole group goes to the embedder at once: it sorts by length
        # internally, and a larger population sorts better.
        if chunk_rows:
            vectors = embedder.embed_documents([r["text"] for r in chunk_rows])
            for row, vec in zip(chunk_rows, vectors, strict=True):
                row["embedding"] = vec
            if progress:
                progress("embed", len(chunk_rows))

        stats.chunks += db.write_batched(CHUNK_WRITE, chunk_rows, batch_size=100)

        # Only now is this group safe to call done.
        db.write_batched(
            """
            UNWIND $rows AS row
            MATCH (f:File {uid: row.uid})
            SET f.sha256 = row.sha, f.loc = row.loc
            """,
            [{"uid": f"{repo}:{f.path}", "sha": f.sha256,
              "loc": parsed_files[f.path].loc if f.path in parsed_files else 0}
             for f in group],
        )

    stats.files_indexed = len(changed)

    # --- edges (repo-wide, needs every symbol present) --------------------
    stats.edges, stats.resolution, stats.test_edges = _write_edges(repo, root)

    if stats.has_history:
        stats.cochange_edges = _write_cochange(repo, root, {f.path for f in files})
    return stats


def _load_all_parsed(repo: str, root: Path) -> dict[str, ParsedFile]:
    """Re-parse the whole repo for the resolution pass.

    Edges are repo-wide: a call in an untouched file may now bind to a symbol
    that only appeared in this run, so partial input would produce wrong
    answers. Parsing is cheap relative to embedding, so this is re-done rather
    than cached.
    """
    rows = db.read(
        "MATCH (f:File {repo: $repo}) RETURN f.path AS path, f.lang AS lang",
        repo=repo,
    )
    work = [(r["path"], str(root / r["path"]), r["lang"]) for r in rows]
    out: dict[str, ParsedFile] = {}
    for item in work:
        path, parsed, _ = _parse_one(item)
        if parsed is not None:
            out[path] = parsed
    return out


def _write_edges(repo: str, root: Path) -> tuple[int, dict[str, int], int]:
    parsed_files = _load_all_parsed(repo, root)
    resolver = Resolver(repo, parsed_files)
    edges, resolution = resolver.resolve_all()

    # Drop the previous generation before rewriting, otherwise stale edges
    # from deleted code survive forever.
    with db.session() as sess:
        sess.run(
            "MATCH (:Symbol {repo: $repo})-[r:CALLS|REFERENCES|INHERITS]->() DELETE r",
            repo=repo,
        ).consume()

    calls = [e for e in edges if e.via == "call"]
    bases = [e for e in edges if e.via == "base"]
    others = [e for e in edges if e.via not in ("call", "base")]

    written = 0
    written += db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (a:Symbol {id: row.src}), (b:Symbol {id: row.dst})
        MERGE (a)-[r:CALLS]->(b) SET r.resolved = true
        """,
        [{"src": e.src_id, "dst": e.dst_id} for e in calls],
    )
    written += db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (a:Symbol {id: row.src}), (b:Symbol {id: row.dst})
        MERGE (a)-[:INHERITS]->(b)
        """,
        [{"src": e.src_id, "dst": e.dst_id} for e in bases],
    )
    written += db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (a:Symbol {id: row.src}), (b:Symbol {id: row.dst})
        MERGE (a)-[r:REFERENCES {via: row.via}]->(b)
        """,
        [{"src": e.src_id, "dst": e.dst_id, "via": e.via} for e in others],
    )

    # File-level IMPORTS, derived from resolved cross-file references.
    import_rows = {
        (e.src_id.split(":")[1], e.dst_id.split(":")[1]) for e in edges
    }
    import_rows = {(a, b) for a, b in import_rows if a != b}
    with db.session() as sess:
        sess.run(
            "MATCH (:File {repo: $repo})-[r:IMPORTS]->() DELETE r", repo=repo
        ).consume()
    written += db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (a:File {uid: row.repo + ':' + row.src}),
              (b:File {uid: row.repo + ':' + row.dst})
        MERGE (a)-[:IMPORTS]->(b)
        """,
        [{"repo": repo, "src": a, "dst": b} for a, b in import_rows],
    )

    # --- TESTED_BY --------------------------------------------------------
    test_rows = db.read(
        "MATCH (f:File {repo: $repo}) WHERE f.is_test RETURN f.path AS path",
        repo=repo,
    )
    test_paths = {r["path"] for r in test_rows}
    test_edges = testlink.derive(repo, parsed_files, test_paths, resolver)

    with db.session() as sess:
        sess.run(
            "MATCH (:Symbol {repo: $repo})-[r:TESTED_BY]->() DELETE r", repo=repo
        ).consume()
    db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (target:Symbol {id: row.target}), (test:Symbol {id: row.test})
        MERGE (target)-[r:TESTED_BY]->(test) SET r.confidence = row.confidence
        """,
        [{"target": e.target_id, "test": e.test_id, "confidence": e.confidence}
         for e in test_edges],
    )
    return written, resolution, len(test_edges)


def _write_cochange(repo: str, root: Path, tracked: set[str]) -> int:
    """Mine and store file-level co-change.

    Stored on :File rather than :Symbol because symbol-level co-change would
    need `git log -L` per symbol, which is far too slow. Symbols inherit it at
    query time by projecting through DEFINES.
    """
    edges = gitmine.mine(root, tracked, git_root=git_root(root))
    with db.session() as sess:
        sess.run(
            "MATCH (:File {repo: $repo})-[r:CO_CHANGED]->() DELETE r", repo=repo
        ).consume()
    db.write_batched(
        """
        UNWIND $rows AS row
        MATCH (a:File {uid: row.repo + ':' + row.src}),
              (b:File {uid: row.repo + ':' + row.dst})
        MERGE (a)-[r:CO_CHANGED]->(b)
        SET r.count = row.count, r.last_seen = row.last_seen, r.weight = row.weight
        """,
        [{"repo": repo, "src": e.src, "dst": e.dst, "count": e.count,
          "last_seen": e.last_seen, "weight": e.weight} for e in edges],
    )
    return len(edges)


def _reparse_for_stats_only(repo: str) -> dict[str, int]:
    rows = db.read(
        """
        MATCH (:Symbol {repo: $repo})-[r:CALLS]->()
        RETURN count(r) AS resolved
        """,
        repo=repo,
    )
    return {"resolved": rows[0]["resolved"] if rows else 0, "unresolved": 0, "total": 0}
