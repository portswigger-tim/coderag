"""Neo4j access: driver lifecycle, schema management, batched writes."""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from neo4j import Driver, GraphDatabase, NotificationDisabledClassification
from neo4j.exceptions import ClientError, ServiceUnavailable

from coderag import schema as ddl
from coderag.config import get_settings

# Community Edition serves exactly one user database, and that is the
# deployment this ships with, so the name is fixed rather than configurable.
DATABASE = "neo4j"

# Rows per write transaction. Neo4j absorbs ~2,150 chunks/sec at this size,
# roughly 47x faster than the embedder can feed it, so the write path is
# nowhere near the bottleneck and there is nothing here worth tuning.
WRITE_BATCH_SIZE = 500

# Nodes per delete transaction. Deleting a whole repo at once overruns
# Neo4j's transaction memory ceiling; this keeps each commit small and
# bounded regardless of repo size.
DELETE_BATCH_SIZE = 10_000

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            # Authentication is disabled on the local-only database this
            # ships with; None means "send no credentials" rather than
            # "send empty ones", which is what the server expects.
            auth=None,
            # On a fresh database every property is "unknown" to the planner,
            # which makes it warn about each one. Those warnings are noise, not
            # signal, and they drown real output.
            notifications_disabled_classifications=[
                NotificationDisabledClassification.UNRECOGNIZED,
                NotificationDisabledClassification.GENERIC,
            ],
        )
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def session() -> Iterator[Any]:
    with get_driver().session(database=DATABASE) as sess:
        yield sess


def wait_until_ready(timeout: float = 90.0, interval: float = 2.0) -> bool:
    """Poll until Neo4j accepts queries.

    The container reports healthy before Bolt is reliably answering, so a
    connect-and-query loop is the only honest readiness check.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with session() as sess:
                sess.run("RETURN 1").consume()
            return True
        except (ServiceUnavailable, OSError, ClientError) as exc:
            last_error = exc
            close_driver()
            time.sleep(interval)
    if last_error:
        raise TimeoutError(
            f"Neo4j not reachable within {timeout:.0f}s: {last_error}\n"
            "Check it is running and did not exit at startup:\n"
            "  docker compose ps -a\n"
            "  docker compose logs neo4j | tail -20\n"
            "A common cause is heap + pagecache exceeding the Docker VM's "
            "memory, which makes Neo4j exit instead of starting."
        )
    return False


def ensure_schema(dim: int) -> None:
    """Create constraints and indexes. Vector index needs the embedding dim."""
    with session() as sess:
        for statement in (*ddl.CONSTRAINTS, *ddl.INDEXES, *ddl.FULLTEXT):
            sess.run(statement).consume()
        sess.run(ddl.vector_index_ddl(dim)).consume()


def drop_vector_index() -> None:
    """Remove the vector index so a bulk load does not maintain it per row."""
    with session() as sess:
        sess.run(ddl.DROP_VECTOR_INDEX).consume()


def await_indexes(timeout: float = 3600.0) -> None:
    """Block until every index finishes populating."""
    with session() as sess:
        sess.run("CALL db.awaitIndexes($t)", t=int(timeout)).consume()


def vector_index_online() -> bool:
    rows = read(
        "SHOW INDEXES YIELD name, state WHERE name = $n RETURN state",
        n=ddl.VECTOR_INDEX_NAME,
    )
    return bool(rows) and rows[0]["state"] == "ONLINE"


# Files, symbols and chunks for a repo, as three independent subqueries.
#
# Written once and shared because the obvious alternative is a trap: three
# chained OPTIONAL MATCH clauses against the same repo read naturally and
# return the right integers -- count(DISTINCT ...) dedupes them -- while
# making the planner materialise files x symbols x chunks rows to do it. On
# one 100-file library that was 140 million rows and 12 seconds to produce
# three numbers. Correct output, so only a profile reveals it.
REPO_COUNTS = (
    "COUNT {{ MATCH (f:File {{repo: {key}}}) }} AS files, "
    "COUNT {{ MATCH (s:Symbol {{repo: {key}}}) }} AS symbols, "
    "COUNT {{ MATCH (c:Chunk {{repo: {key}}}) }} AS chunks"
)


def repo_counts_clause(key: str = "r.name") -> str:
    """The RETURN fragment above, keyed on a repo name expression."""
    return REPO_COUNTS.format(key=key)


def count_chunks(repo: str) -> int:
    rows = read("MATCH (c:Chunk {repo: $repo}) RETURN count(c) AS n", repo=repo)
    return rows[0]["n"] if rows else 0


def drop_schema() -> None:
    with session() as sess:
        for statement in ddl.DROP_ALL:
            try:
                sess.run(statement).consume()
            except ClientError:
                pass


def wipe_repo(repo: str) -> None:
    """Remove a repo and everything hanging off it.

    One label at a time, in bounded batches. The previous version deleted
    everything in a single statement that matched files and chunks in the
    same query -- a cartesian product, 100 files x 1,281 chunks for a small
    library -- and it exceeded dbms.memory.transaction.total.max on any
    real repository, failing partway and leaving the repo half-deleted.
    Batching also keeps a drop interruptible: each batch commits, so a
    cancelled drop resumes rather than rolling back an hour of work.
    """
    with session() as sess:
        for label in ("Chunk", "Symbol", "File"):
            while True:
                deleted = sess.run(
                    f"MATCH (n:{label} {{repo: $repo}}) WITH n LIMIT $limit "
                    "DETACH DELETE n RETURN count(*) AS n",
                    repo=repo, limit=DELETE_BATCH_SIZE,
                ).single()["n"]
                if not deleted:
                    break
        sess.run("MATCH (r:Repo {name: $repo}) DETACH DELETE r", repo=repo).consume()


def write_batched(
    query: str, rows: Iterable[dict[str, Any]], batch_size: int | None = None
) -> int:
    """Run one UNWIND-shaped write per batch. Returns rows written."""
    size = batch_size or WRITE_BATCH_SIZE
    batch: list[dict[str, Any]] = []
    written = 0

    with session() as sess:
        for row in rows:
            batch.append(row)
            if len(batch) >= size:
                sess.execute_write(lambda tx, b=batch: tx.run(query, rows=b).consume())
                written += len(batch)
                batch = []
        if batch:
            sess.execute_write(lambda tx, b=batch: tx.run(query, rows=b).consume())
            written += len(batch)
    return written


def read(query: str, **params: Any) -> list[dict[str, Any]]:
    with session() as sess:
        return [record.data() for record in sess.run(query, **params)]
