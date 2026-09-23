"""Retrieval: hybrid search, then the graph pass that prunes and boosts.

The graph is not here to add more results. It is here to decide which of the
lexical/vector candidates deserve the caller's attention and which are
coincidence -- the same-named symbol in an unrelated module being the classic
case. Expansion is budgeted so a hot symbol cannot blow the response open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from coderag import db
from coderag.pack import (
    Card, Pack, Section, dedupe_by_symbol, normalise_scores, summarise_by_module,
)

# Lucene reserves these; a user query is prose, not a query language.
_LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')

# Default response ceiling, in estimated tokens. Callers that care -- the
# MCP tools -- pass budget_tokens per call instead.
BUDGET_SEARCH = 1500

RRF_K = 60           # standard reciprocal-rank-fusion damping
SEED_POOL = 20       # candidates taken from each retrieval arm

# Question words and filler. In a prose question these are most of the
# query, and none of them discriminate between one piece of code and another.
_STOPWORDS = frozenset("""
a an and are as at be been but by can could do does doing for from get
had has have how i if in into is it its me my of on or our over should
so than that the their them then there these they this those to under
up use used uses using was we were what when where which who why will
with would you your
""".split())

# Lucene's default analyser does not stem, so "persisted" never matches
# "persist". That makes BM25 over a natural-language question mostly noise:
# it ranks on whichever common word happens to appear most, which is rarely
# the answer. Keyword search earns its place on identifiers -- exact names
# a reader already knows -- so the arm is weighted by how identifier-like
# the query actually is.
_IDENTIFIERISH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:[._][A-Za-z0-9_]+)+|[a-z]+[A-Z]\w*")


def _escape_lucene(text: str) -> str:
    return _LUCENE_SPECIAL.sub(r"\\\1", text).strip()


def _lexical_terms(query: str) -> list[str]:
    """Query terms worth handing to BM25, stripped of question filler."""
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", query)
    return [t for t in raw if t.lower() not in _STOPWORDS and len(t) > 2]


def _lexical_weight(repo: str, query: str, terms: list[str]) -> float:
    """How much to trust keyword search for this query.

    Full weight when the query names something that exists -- an identifier
    the user already knows. Heavily reduced for prose, where BM25 ranks on
    incidental word overlap and drags real answers down the list.
    """
    if not terms:
        return 0.0
    if _IDENTIFIERISH.search(query):
        return 1.0
    rows = db.read(
        """
        MATCH (s:Symbol {repo: $repo})
        WHERE toLower(s.name) IN $terms
        RETURN count(s) AS n
        """,
        repo=repo, terms=[t.lower() for t in terms],
    )
    return 1.0 if rows and rows[0]["n"] else 0.25


@dataclass(slots=True)
class Candidate:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    symbol_qname: str | None
    kind: str
    is_test: bool
    score: float = 0.0
    reasons: list[str] = None   # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []


def _vector_arm(repo: str, vector: list[float], limit: int) -> list[Candidate]:
    if not db.vector_index_online():
        raise RuntimeError(
            "the chunk_embedding vector index is missing or still building. "
            "Run `coderag init` to recreate it, then retry. Vector search is "
            "unavailable until it is ONLINE."
        )
    rows = db.read(
        """
        CALL db.index.vector.queryNodes('chunk_embedding', $limit, $vec)
        YIELD node, score
        WHERE node.repo = $repo
        RETURN node.id AS id, node.path AS path, node.start_line AS start_line,
               node.end_line AS end_line, node.symbol_qname AS symbol_qname,
               node.kind AS kind, coalesce(node.is_test, false) AS is_test,
               score
        """,
        repo=repo, vec=vector, limit=limit * 3,
    )
    return [
        Candidate(r["id"], r["path"], r["start_line"], r["end_line"],
                  r["symbol_qname"], r["kind"], r["is_test"], r["score"])
        for r in rows[:limit]
    ]


def _fulltext_arm(repo: str, query: str, limit: int) -> list[Candidate]:
    terms = _lexical_terms(query)
    escaped = _escape_lucene(" ".join(terms))
    if not escaped:
        return []
    rows = db.read(
        """
        CALL db.index.fulltext.queryNodes('chunk_text', $q, {limit: $limit})
        YIELD node, score
        WHERE node.repo = $repo
        RETURN node.id AS id, node.path AS path, node.start_line AS start_line,
               node.end_line AS end_line, node.symbol_qname AS symbol_qname,
               node.kind AS kind, coalesce(node.is_test, false) AS is_test,
               score
        """,
        repo=repo, q=escaped, limit=limit * 3,
    )
    return [
        Candidate(r["id"], r["path"], r["start_line"], r["end_line"],
                  r["symbol_qname"], r["kind"], r["is_test"], r["score"])
        for r in rows[:limit]
    ]


def _fuse(arms: list[tuple[list[Candidate], float]]) -> list[Candidate]:
    """Weighted reciprocal rank fusion.

    Rank-based, so the arms' incomparable score scales never need
    normalising; weighted, so an arm that is untrustworthy for this
    particular query contributes proportionally less.
    """
    merged: dict[str, Candidate] = {}
    for arm, weight in arms:
        if weight <= 0:
            continue
        for rank, cand in enumerate(arm, start=1):
            existing = merged.get(cand.chunk_id)
            if existing is None:
                cand.score = 0.0
                merged[cand.chunk_id] = cand
                existing = cand
            existing.score += weight / (RRF_K + rank)
    return sorted(merged.values(), key=lambda c: -c.score)


def _graph_pass(repo: str, candidates: list[Candidate]) -> list[Candidate]:
    """Prune coincidences, boost structurally-connected candidates.

    A candidate whose symbol has no call, reference or containment relation to
    any other candidate in the pool, and which ranked below the leader by a
    wide margin, is far more likely to be a name collision than an answer.
    """
    qnames = [c.symbol_qname for c in candidates if c.symbol_qname]
    if len(qnames) < 2:
        return candidates

    rows = db.read(
        """
        MATCH (a:Symbol {repo: $repo})-[r:CALLS|REFERENCES|DEFINES|INHERITS]-(b:Symbol {repo: $repo})
        WHERE a.qname IN $qnames AND b.qname IN $qnames
        RETURN DISTINCT a.qname AS src, b.qname AS dst
        """,
        repo=repo, qnames=qnames,
    )
    connected: set[str] = set()
    for row in rows:
        connected.add(row["src"])
        connected.add(row["dst"])

    if not connected:
        return candidates

    best = candidates[0].score if candidates else 0.0
    kept: list[Candidate] = []
    for cand in candidates:
        if cand.symbol_qname in connected:
            cand.score *= 1.35
            cand.reasons.append("structurally connected")
            kept.append(cand)
        elif cand.score >= best * 0.55:
            kept.append(cand)          # strong enough to stand alone
        # else: weak *and* unconnected -> dropped as a likely name collision
    return sorted(kept, key=lambda c: -c.score)


def _expand(
    repo: str, candidates: list[Candidate], limit: int = 6, hop_decay: float = 0.45
) -> list[Candidate]:
    """Pull in symbols one hop from the strongest seeds.

    This is the half of the thesis that pruning alone cannot deliver. A
    question like "what happens when an order is placed" names one step of a
    chain; the rest of the chain shares none of its vocabulary and no amount
    of lexical or vector matching will surface it. One hop along CALLS in
    both directions does, cheaply and with a stated reason.
    """
    seeds = [c for c in candidates[:5] if c.symbol_qname]
    if not seeds:
        return candidates

    known = {c.symbol_qname for c in candidates if c.symbol_qname}
    seed_scores = {c.symbol_qname: c.score for c in seeds}

    rows = db.read(
        """
        MATCH (seed:Symbol {repo: $repo})-[:CALLS]-(neighbour:Symbol {repo: $repo})
        WHERE seed.qname IN $seeds AND NOT neighbour.qname IN $known
          AND NOT coalesce(neighbour.is_test, false)
        RETURN DISTINCT neighbour.qname AS qname, neighbour.path AS path,
               neighbour.start_line AS start_line, neighbour.end_line AS end_line,
               neighbour.kind AS kind, seed.qname AS seed
        """,
        repo=repo, seeds=list(seed_scores), known=list(known),
    )

    added: dict[str, Candidate] = {}
    for row in rows:
        base = seed_scores.get(row["seed"], 0.0) * hop_decay
        existing = added.get(row["qname"])
        if existing is not None and existing.score >= base:
            continue
        short_seed = row["seed"].rsplit(".", 1)[-1]
        added[row["qname"]] = Candidate(
            chunk_id=f"expanded:{row['qname']}",
            path=row["path"],
            start_line=row["start_line"] or 0,
            end_line=row["end_line"] or 0,
            symbol_qname=row["qname"],
            kind=row["kind"] or "",
            is_test=False,
            score=base,
            reasons=[f"1 hop from {short_seed}"],
        )

    best = sorted(added.values(), key=lambda c: -c.score)[:limit]
    return sorted([*candidates, *best], key=lambda c: -c.score)


def _cards_for(repo: str, candidates: list[Candidate], seed_query: str) -> list[Card]:
    qnames = [c.symbol_qname for c in candidates if c.symbol_qname]
    meta: dict[str, dict] = {}
    if qnames:
        rows = db.read(
            """
            MATCH (s:Symbol {repo: $repo}) WHERE s.qname IN $qnames
            OPTIONAL MATCH (s)<-[:CALLS]-(caller:Symbol)
            OPTIONAL MATCH (s)<-[:DEFINES]-(parent:Symbol)
            RETURN s.qname AS qname, s.signature AS signature, s.kind AS kind,
                   s.start_line AS start_line, s.end_line AS end_line,
                   s.path AS path, parent.name AS parent,
                   count(DISTINCT caller) AS callers
            """,
            repo=repo, qnames=qnames,
        )
        meta = {r["qname"]: r for r in rows}

    cards: list[Card] = []
    for cand in candidates:
        info = meta.get(cand.symbol_qname or "", {})
        placement_bits = []
        if info.get("parent"):
            placement_bits.append(f"in class {info['parent']}")
        if info.get("callers"):
            placement_bits.append(f"{info['callers']} caller(s)")
        reasons = list(cand.reasons)
        cards.append(
            Card(
                qname=cand.symbol_qname or f"{cand.path} (module level)",
                path=cand.path,
                start_line=info.get("start_line") or cand.start_line,
                end_line=info.get("end_line") or cand.end_line,
                kind=info.get("kind") or cand.kind,
                signature=info.get("signature") or "",
                reason=" | ".join(reasons) if reasons else "",
                placement=" | ".join(placement_bits),
                score=cand.score,
            )
        )
    return cards


def search(
    query: str,
    repo: str,
    embedder,
    k: int = 8,
    scope: str | None = None,
    include_tests: bool = False,
    expand: bool = True,
    budget_tokens: int | None = None,
) -> Pack:
    budget = budget_tokens or BUDGET_SEARCH

    vector = embedder.embed_query(query)
    lex_weight = _lexical_weight(repo, query, _lexical_terms(query))
    candidates = _fuse([
        (_vector_arm(repo, vector, SEED_POOL), 1.0),
        (_fulltext_arm(repo, query, SEED_POOL), lex_weight),
    ])

    # A named symbol is almost always a better answer than an anonymous
    # stretch of module-level code that merely mentions the right words.
    for cand in candidates:
        if cand.symbol_qname is None:
            cand.score *= 0.55

    if scope:
        candidates = [c for c in candidates if c.path.startswith(scope)]
    if not include_tests:
        # Kept, but demoted: tests answer test questions, not "how does this work".
        for cand in candidates:
            if cand.is_test:
                cand.score *= 0.35

    if expand:
        candidates = _graph_pass(repo, candidates)
        candidates = _expand(repo, candidates)

    candidates = sorted(candidates, key=lambda c: -c.score)
    cards = dedupe_by_symbol(_cards_for(repo, candidates, query))
    normalise_scores(cards)
    for card in cards:
        prefix = f"relevance {card.score:.2f}"
        card.reason = f"{prefix} | {card.reason}" if card.reason else prefix

    pack = Pack(
        title=f'SEARCH  "{query}"',
        budget_tokens=budget,
        total_available=len(cards),
    )
    pack.sections.append(Section(title="", cards=cards[:k]))

    # Hierarchical fallback is a response to budget pressure, not to breadth.
    # If the top-k cards fit, listing them is always more useful than naming
    # the modules they live in.
    shown_cost = sum(card.tokens() for card in cards[:k])
    if shown_cost > budget:
        wide = summarise_by_module(cards)
        if wide is not None:
            pack.sections = [wide]
            pack.total_available = len(cards)
            pack.notes.append("too many matches to list individually")

    if not expand:
        pack.notes.append("graph pass disabled")
    return pack
