"""MCP stdio server.

Tool descriptions state the intended sequence explicitly -- locate, then
understand, then check the blast radius -- so the model does not have to
infer a workflow from tool names. Every tool returns budgeted text pointing
at line ranges; none of them return whole files.
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from coderag import db
from coderag.context import (
    file_context,
    symbol_context,
    what_breaks,
    what_tests,
    who_calls,
)
from coderag.embedder import get_embedder
from coderag.retriever import search as run_search

CODERAG_REPO = os.environ.get("CODERAG_REPO")


class RepoNotResolved(RuntimeError):
    """Raised with text the model can act on, not a stack trace."""


def _repo(repo: str | None) -> str:
    """Which repo a tool call is about.

    An explicit argument wins, then CODERAG_REPO, then the only indexed
    repo if there is exactly one. Nothing falls back to a bundled sample:
    answering confidently about the wrong repository is worse than saying
    which ones exist.
    """
    if repo:
        return repo
    if CODERAG_REPO:
        return CODERAG_REPO
    names = [r["name"] for r in db.read(
        "MATCH (r:Repo) RETURN r.name AS name ORDER BY r.name")]
    if len(names) == 1:
        return names[0]
    if not names:
        raise RepoNotResolved(
            "nothing is indexed yet. Run: coderag index <path> --repo <name>"
        )
    raise RepoNotResolved(
        "several repositories are indexed; pass repo= explicitly. "
        "Available: " + ", ".join(names)
    )

server = MCPServer(
    name="coderag",
    instructions=(
        "Code navigation over an indexed repository, designed to keep context "
        "small. Prefer these tools over grep and over reading whole files.\n\n"
        "Normal sequence:\n"
        "  1. search_code  - find where something lives\n"
        "  2. symbol_context - understand what it is embedded in, before editing\n"
        "  3. what_breaks  - check the blast radius of a change\n"
        "  4. Read only the specific line ranges the tools cite.\n\n"
        "Every result cites path:line ranges. Read those ranges rather than "
        "whole files: file_context gives a file's outline for a fraction of "
        "the cost of reading it."
    ),
)

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = get_embedder()
    return _embedder


@server.tool(
    description=(
        "Find code by meaning or by name. Returns ranked symbols with their "
        "signature, path:line range, and why each was selected. Start here when "
        "you do not yet know where something lives. Results are pointers: read "
        "the line ranges you actually need."
    )
)
def search_code(
    query: str,
    repo: str | None = None,
    k: int = 8,
    scope: str | None = None,
    include_tests: bool = False,
    budget_tokens: int | None = None,
) -> str:
    """Hybrid vector and keyword search, pruned and ranked by the code graph."""
    db.wait_until_ready()
    pack = run_search(
        query, repo=_repo(repo), embedder=_get_embedder(), k=k, scope=scope,
        include_tests=include_tests, expand=True, budget_tokens=budget_tokens,
    )
    return pack.render()


@server.tool(
    name="symbol_context",
    description=(
        "Everything needed to change one symbol safely, in a single call: its "
        "signature, the class it belongs to and that class's other methods, the "
        "types and config it depends on (small types are inlined), what calls "
        "it, which tests cover it, and which files historically change "
        "alongside it. Call this before editing any symbol."
    )
)
def symbol_context_tool(
    qname: str, repo: str | None = None, budget_tokens: int | None = None
) -> str:
    """The neighbourhood of one symbol, inward and outward."""
    db.wait_until_ready()
    return symbol_context(_repo(repo), qname, budget_tokens=budget_tokens).render()


@server.tool(
    name="what_breaks",
    description=(
        "Blast radius of changing a symbol: transitive callers, the tests that "
        "would run, and files that historically change together with it. The "
        "last of those catches coupling with no import or call between the "
        "files -- config, fixtures, generated artefacts."
    )
)
def what_breaks_tool(
    qname: str, repo: str | None = None, depth: int = 2,
    budget_tokens: int | None = None,
) -> str:
    """What a change to this symbol would affect."""
    db.wait_until_ready()
    return what_breaks(_repo(repo), qname, depth=depth, budget_tokens=budget_tokens).render()


@server.tool(
    name="what_tests",
    description=(
        "Which tests cover a symbol, strongest evidence first. Use before "
        "changing behaviour, and to find the right place to add a case."
    )
)
def what_tests_tool(qname: str, repo: str | None = None) -> str:
    """Covering tests for a symbol."""
    db.wait_until_ready()
    return what_tests(_repo(repo), qname).render()


@server.tool(
    name="who_calls",
    description=(
        "Inbound call tree for a symbol, up to N hops. Use when you need the "
        "path from an entry point down to this code."
    )
)
def who_calls_tool(qname: str, repo: str | None = None, depth: int = 2) -> str:
    """Who calls this symbol."""
    db.wait_until_ready()
    return who_calls(_repo(repo), qname, depth=depth).render()


@server.tool(
    name="file_context",
    description=(
        "A file's outline: every symbol with its signature and line range, plus "
        "what imports it and what it co-changes with -- and no bodies. Use this "
        "INSTEAD OF reading a file you are unfamiliar with: a 3,000-line file "
        "costs tens of thousands of tokens to read and a few hundred to outline."
    )
)
def file_context_tool(
    path: str, repo: str | None = None, budget_tokens: int | None = None
) -> str:
    """A file's structure without its contents."""
    db.wait_until_ready()
    return file_context(_repo(repo), path, budget_tokens=budget_tokens).render()


@server.tool(
    description=(
        "What is indexed: repositories, file and symbol counts, whether git "
        "history was available for co-change, and how much of the call graph "
        "resolved. Check this if results look thin or stale."
    )
)
def index_status() -> str:
    """Index health and coverage."""
    db.wait_until_ready()
    rows = db.read(
        """
        MATCH (r:Repo)
        RETURN r.name AS repo, r.embedder AS embedder, r.dim AS dim,
               coalesce(r.has_history, false) AS has_history,
               toString(r.indexed_at) AS indexed_at,
               COUNT { MATCH (f:File {repo: r.name}) } AS files,
               COUNT { MATCH (s:Symbol {repo: r.name}) } AS symbols,
               COUNT { MATCH (c:Chunk {repo: r.name}) } AS chunks
        ORDER BY r.name
        """
    )
    if not rows:
        return "nothing indexed - run: coderag index <path> --repo <name>\n"

    out = []
    for row in rows:
        edges = db.read(
            """
            MATCH (:Symbol {repo: $repo})-[e]->(:Symbol {repo: $repo})
            RETURN type(e) AS kind, count(e) AS n ORDER BY n DESC
            """,
            repo=row["repo"],
        )
        cochange = db.read(
            "MATCH (:File {repo: $repo})-[e:CO_CHANGED]->() RETURN count(e) AS n",
            repo=row["repo"],
        )
        edge_text = ", ".join(f"{e['kind']}={e['n']}" for e in edges) or "none"
        out.append(
            f"{row['repo']}: {row['files']} files, {row['symbols']} symbols, "
            f"{row['chunks']} chunks\n"
            f"  edges: {edge_text}, CO_CHANGED={cochange[0]['n'] if cochange else 0}\n"
            f"  embedder: {row['embedder']} (dim {row['dim']})\n"
            f"  git history: {'yes' if row['has_history'] else 'no (co-change unavailable)'}\n"
            f"  indexed at: {row['indexed_at']}"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
