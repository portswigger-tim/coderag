"""Shared fixtures.

Everything here is opt-in. The default `uv run pytest` runs no Docker and
no database; the integration tier is selected with `-m neo4j`.
"""

from __future__ import annotations

import hashlib

import pytest

from coderag.embedder import DIM


class StubEmbedder:
    """Deterministic vectors, no model.

    The integration tier exists to test Neo4j -- schema, traversal, deletion,
    repo isolation -- not the embedder, which the unit tier and the eval
    harness already cover. Loading a real 67 MB ONNX model would add a
    download and tens of seconds per run to test none of that. Vectors are
    derived from the text so they are stable across runs and identical text
    embeds identically, which is all the graph layer needs.
    """

    name = "stub"
    dim = DIM
    model_id = "stub"

    def warm(self) -> None:
        return None

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = (digest * ((self.dim // len(digest)) + 1))[: self.dim]
        return [(b - 127.5) / 127.5 for b in raw]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@pytest.fixture(scope="session")
def neo4j_uri() -> str:
    """A throwaway Neo4j, matching what docker-compose.yml ships.

    Same image and the same auth-disabled configuration, so the tier tests
    the deployment the project actually uses rather than a convenient
    approximation. One container per session, about thirteen seconds for
    the whole tier.

    There is deliberately no environment variable to point this at an
    already-running database. It existed while the container path was
    broken, and a second way to obtain a fixture is a second thing that
    can silently disagree with the first -- a developer whose local
    instance has stale schema or leftover data would get results nobody
    else can reproduce.
    """
    core = pytest.importorskip(
        "testcontainers.core.container", reason="testcontainers not installed"
    )
    # Deliberately the generic container rather than Neo4jContainer. That
    # helper sets NEO4J_AUTH=neo4j/<password> in its constructor and waits
    # for readiness using those credentials, so asking it for an unauthenticated
    # database fights it -- the server logs "Changed password for user 'neo4j'.
    # IMPORTANT: this change will only take effect if performed before the
    # database is started for the first time." and the configurations diverge.
    # coderag ships an auth-disabled database, and the tier should test that,
    # not a differently-configured approximation of it.
    container = (
        core.DockerContainer("neo4j:5.26-community")
        .with_env("NEO4J_AUTH", "none")
        .with_env("NEO4J_server_jvm_additional", "--add-modules jdk.incubator.vector")
        .with_exposed_ports(7687)
    )
    with container as running:
        host = running.get_container_host_ip()
        port = running.get_exposed_port(7687)
        # No log-waiting: db.wait_until_ready already polls with a real query,
        # which is the only honest readiness check for Bolt.
        yield f"bolt://{host}:{port}"


@pytest.fixture()
def db(neo4j_uri, monkeypatch):
    """coderag's db module, pointed at the throwaway instance and reset.

    Settings and driver are process-wide singletons, so both are cleared:
    without that a test would silently reuse a connection to whatever the
    developer happens to be running locally.
    """
    from coderag import config
    from coderag import db as db_module

    monkeypatch.setenv("NEO4J_URI", neo4j_uri)
    config._settings = None
    db_module.close_driver()

    db_module.wait_until_ready(timeout=120)
    # Each test starts from an empty graph but keeps the schema, which is
    # how the tool behaves between runs.
    db_module.read("MATCH (n) DETACH DELETE n")
    db_module.ensure_schema(DIM)
    db_module.await_indexes(timeout=120)

    yield db_module

    db_module.close_driver()
    config._settings = None


@pytest.fixture()
def embedder() -> StubEmbedder:
    return StubEmbedder()
