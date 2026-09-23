"""The half of coderag the DB-free suite cannot reach.

Everything here needs a real Neo4j: the Cypher, the schema, the traversals
that make symbol_context and what_breaks possible, and deletion. Those are
roughly half the codebase and, until this tier existed, none of it was
covered -- the `neo4j` marker was declared in pyproject.toml and unused.

Two of the bugs asserted against here shipped and were found by hand:
`wipe_repo` overrunning Neo4j's transaction memory on any real repository,
and the repo-counting queries materialising a cartesian product. Both
returned correct answers on the tiny bundled sample, which is exactly why
neither the unit tier nor the eval harness noticed.

Run with:  uv run pytest -m neo4j
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coderag.embedder import DIM

pytestmark = pytest.mark.neo4j

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "python"


@pytest.fixture()
def indexed(db, embedder):
    """The Python sample, indexed under one repo."""
    from coderag.indexer import index_repo

    stats = index_repo(SAMPLE, repo="t", embedder=embedder)
    assert stats.files_indexed > 0
    return stats


# --- schema ---------------------------------------------------------------


def test_schema_creates_every_declared_index(db):
    """A missing index is silent: queries still answer, just by scanning."""
    names = {r["name"] for r in db.read("SHOW INDEXES YIELD name RETURN name")}
    for required in (
        "chunk_embedding",   # vector search is impossible without it
        "symbol_repo",       # every context tool anchors on (Symbol {repo})
        "chunk_repo",
        "file_repo",
        "symbol_qname",
        "symbol_id",
        "file_uid",
        "chunk_id",
        "repo_name",
        "chunk_text",
        "symbol_search",
    ):
        assert required in names, f"{required} missing from the schema"


def test_vector_index_is_online_and_correctly_dimensioned(db):
    rows = db.read(
        "SHOW INDEXES YIELD name, state, options WHERE name = 'chunk_embedding' "
        "RETURN state, options"
    )
    assert rows and rows[0]["state"] == "ONLINE"
    config = rows[0]["options"]["indexConfig"]
    assert config["vector.dimensions"] == DIM


# --- indexing and retrieval ----------------------------------------------


def test_index_then_search_finds_the_right_symbol(db, embedder, indexed):
    from coderag.retriever import search

    pack = search(
        "apply_bulk_discount", repo="t", embedder=embedder, k=8, expand=True
    )
    assert "apply_bulk_discount" in pack.render()


def test_symbol_context_traverses_the_graph(db, embedder, indexed):
    """None of these sections exist without traversable relationships."""
    from coderag.context import symbol_context

    rendered = symbol_context(
        "t", "services.pricing.PricingService.apply_bulk_discount"
    ).render()
    assert "apply_bulk_discount" in rendered
    assert "services/pricing.py" in rendered


def test_what_breaks_finds_callers(db, embedder, indexed):
    from coderag.context import what_breaks

    rendered = what_breaks(
        "t", "services.pricing.PricingService.apply_bulk_discount"
    ).render()
    assert "place_order" in rendered


def test_missing_symbol_is_reported_not_raised(db, embedder, indexed):
    from coderag.context import symbol_context

    rendered = symbol_context("t", "no.such.symbol").render()
    assert "no symbol matching" in rendered


# --- repo isolation -------------------------------------------------------


def test_repos_do_not_leak_into_each_other(db, embedder):
    """Edges are keyed on '{repo}:{path}:{name}' so they cannot span repos.

    That invariant is what lets the traversals leave their far end
    unfiltered, so it is worth asserting rather than assuming.
    """
    from coderag.indexer import index_repo
    from coderag.retriever import search

    index_repo(SAMPLE, repo="alpha", embedder=embedder)
    index_repo(SAMPLE, repo="beta", embedder=embedder)

    crossing = db.read(
        """
        MATCH (a:Symbol {repo: 'alpha'})-[r]-(b:Symbol {repo: 'beta'})
        RETURN count(r) AS n
        """
    )[0]["n"]
    assert crossing == 0

    pack = search("apply_bulk_discount", repo="alpha", embedder=embedder, k=8)
    for section in pack.sections:
        for card in section.cards:
            assert "beta" not in (card.qname or "")


# --- the two bugs that shipped -------------------------------------------


def test_wipe_repo_leaves_nothing_behind(db, embedder, indexed):
    """The original deleted files and chunks in one cartesian statement.

    It overran dbms.memory.transaction.total.max on any real repository and
    failed partway, leaving the repo half-deleted.
    """
    db.wipe_repo("t")
    for label, key in (("File", "repo"), ("Symbol", "repo"),
                       ("Chunk", "repo"), ("Repo", "name")):
        remaining = db.read(
            f"MATCH (n:{label} {{{key}: 't'}}) RETURN count(n) AS n"
        )[0]["n"]
        assert remaining == 0, f"{label} survived the drop"


def test_wipe_repo_deletes_in_batches(db, embedder, indexed, monkeypatch):
    """Each batch commits, so the delete is bounded and interruptible."""
    monkeypatch.setattr(db, "DELETE_BATCH_SIZE", 2)
    before = db.read("MATCH (c:Chunk {repo: 't'}) RETURN count(c) AS n")[0]["n"]
    assert before > 2, "fixture too small to exercise the loop"

    db.wipe_repo("t")
    assert db.read("MATCH (c:Chunk {repo: 't'}) RETURN count(c) AS n")[0]["n"] == 0


def test_wipe_repo_spares_other_repos(db, embedder):
    from coderag.indexer import index_repo

    index_repo(SAMPLE, repo="keep", embedder=embedder)
    index_repo(SAMPLE, repo="drop", embedder=embedder)
    kept_before = db.read("MATCH (c:Chunk {repo: 'keep'}) RETURN count(c) AS n")[0]["n"]

    db.wipe_repo("drop")

    assert db.read("MATCH (c:Chunk {repo: 'drop'}) RETURN count(c) AS n")[0]["n"] == 0
    assert db.read(
        "MATCH (c:Chunk {repo: 'keep'}) RETURN count(c) AS n"
    )[0]["n"] == kept_before


def counts_query(db_module) -> str:
    """The production counting clause, not a copy of it.

    Written this way on purpose: an earlier draft inlined the COUNT{} form
    here, which would have kept passing if cli.py and mcp_server.py were
    reverted to chained OPTIONAL MATCH. A guard that does not read the
    shipped query guards nothing.
    """
    return "MATCH (r:Repo) RETURN r.name AS name, " + db_module.repo_counts_clause()


def _profile_rows(db_module, query: str) -> int:
    """Total rows the planner actually pushed through every operator."""
    with db_module.session() as sess:
        summary = sess.run("PROFILE " + query).consume()
    total, stack = 0, [summary.profile]
    while stack:
        node = stack.pop()
        total += node.get("rows", 0)
        stack.extend(node.get("children", []))
    return total


def test_repo_counts_are_correct(db, embedder, indexed):
    row = next(r for r in db.read(counts_query(db)) if r["name"] == "t")
    assert row["files"] == indexed.files_indexed
    assert row["chunks"] == indexed.chunks
    assert row["symbols"] > 0


def test_repo_counts_do_not_build_a_cartesian_product(db, embedder, indexed):
    """The bug this guards was invisible to correctness checks.

    Counting three unrelated collections with chained OPTIONAL MATCH gives
    the right integers -- count(DISTINCT ...) dedupes them -- while
    materialising files x symbols x chunks rows to do it. On one 100-file
    library that was 140 million rows and 12 seconds to produce three
    numbers. Only the work done, not the answer, reveals it.
    """
    row = next(r for r in db.read(counts_query(db)) if r["name"] == "t")
    product = row["files"] * row["symbols"] * row["chunks"]
    assert product > 1000, "fixture too small for the assertion to mean anything"

    rows_processed = _profile_rows(db, counts_query(db))
    budget = 20 * (row["files"] + row["symbols"] + row["chunks"])
    assert rows_processed < budget, (
        f"{rows_processed} rows to count {row['files']} files, "
        f"{row['symbols']} symbols, {row['chunks']} chunks "
        f"-- looks like a cartesian product (would be ~{product})"
    )


# --- re-indexing ----------------------------------------------------------


def test_reindex_is_idempotent(db, embedder, indexed):
    """Unchanged files are skipped by content hash; nothing duplicates."""
    from coderag.indexer import index_repo

    again = index_repo(SAMPLE, repo="t", embedder=embedder)
    assert again.files_skipped == indexed.files_indexed
    assert again.files_indexed == 0

    chunks = db.read("MATCH (c:Chunk {repo: 't'}) RETURN count(c) AS n")[0]["n"]
    assert chunks == indexed.chunks
