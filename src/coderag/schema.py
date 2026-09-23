"""Constraints and indexes. Idempotent -- safe to run on every startup."""

from __future__ import annotations

CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT repo_name IF NOT EXISTS FOR (r:Repo) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT file_uid IF NOT EXISTS FOR (f:File) REQUIRE f.uid IS UNIQUE",
    "CREATE CONSTRAINT symbol_id IF NOT EXISTS FOR (s:Symbol) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
)

# Plain lookup indexes for the traversal hot paths.
#
# symbol_repo matters because every context tool starts by resolving a name
# within one repo, and every search weighs its lexical arm the same way --
# both anchor on (s:Symbol {repo: ...}). Without the index that is a scan of
# every symbol in the database, not just the repo's: measured at 7,755
# symbols, _find_symbol 2.69ms -> 1.73ms and the search-time lexical weight
# 3.08ms -> 1.64ms. The gap grows with everything else indexed alongside.
INDEXES: tuple[str, ...] = (
    "CREATE INDEX symbol_qname IF NOT EXISTS FOR (s:Symbol) ON (s.qname)",
    "CREATE INDEX symbol_name IF NOT EXISTS FOR (s:Symbol) ON (s.name)",
    "CREATE INDEX symbol_repo IF NOT EXISTS FOR (s:Symbol) ON (s.repo)",
    "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX file_repo IF NOT EXISTS FOR (f:File) ON (f.repo)",
    "CREATE INDEX chunk_repo IF NOT EXISTS FOR (c:Chunk) ON (c.repo)",
)

FULLTEXT: tuple[str, ...] = (
    "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
    "CREATE FULLTEXT INDEX symbol_search IF NOT EXISTS FOR (s:Symbol) "
    "ON EACH [s.name, s.qname, s.docstring]",
)

VECTOR_INDEX_NAME = "chunk_embedding"


def vector_index_ddl(dim: int) -> str:
    """Vector index DDL. Dimension is fixed at creation, hence the re-index rule."""
    return (
        f"CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS "
        "FOR (c:Chunk) ON (c.embedding) "
        "OPTIONS {indexConfig: {"
        f"`vector.dimensions`: {dim}, "
        "`vector.similarity_function`: 'cosine'}}"
    )


DROP_VECTOR_INDEX = f"DROP INDEX {VECTOR_INDEX_NAME} IF EXISTS"


DROP_ALL: tuple[str, ...] = (
    f"DROP INDEX {VECTOR_INDEX_NAME} IF EXISTS",
    "DROP INDEX chunk_text IF EXISTS",
    "DROP INDEX symbol_search IF EXISTS",
)
