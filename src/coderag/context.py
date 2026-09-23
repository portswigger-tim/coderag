"""Neighbourhood assembly: the tools that answer "what do I need to know".

search_code answers *where*. These answer *what is this embedded in* and
*what would my change break* -- the two halves an agent needs before editing
anything. Both directions are budgeted and both cite line ranges rather than
reproducing code, except where inlining is genuinely cheaper.
"""

from __future__ import annotations

from pathlib import Path

from coderag import db
from coderag.pack import Card, Pack, Section, collapse_by_file, estimate_tokens

# Default response ceilings, in estimated tokens. The MCP tools override
# these per call via budget_tokens, which is the only place a caller has a
# real reason to care.
BUDGET_SYMBOL_CONTEXT = 1200
BUDGET_WHAT_BREAKS = 1500
BUDGET_FILE_CONTEXT = 2000

# A referenced symbol shorter than this is inlined into a pack rather than
# pointed at, because a pointer would cost the agent a Read larger than the
# definition itself.
INLINE_MAX_LINES = 15


def _repo_root(repo: str) -> Path | None:
    rows = db.read("MATCH (r:Repo {name: $repo}) RETURN r.root AS root", repo=repo)
    return Path(rows[0]["root"]) if rows and rows[0]["root"] else None


def _read_lines(root: Path | None, path: str, start: int, end: int) -> str | None:
    """Pull an exact line range off disk for inlining."""
    if root is None:
        return None
    try:
        lines = (root / path).read_text(errors="replace").splitlines()
    except OSError:
        return None
    if start < 1 or start > len(lines):
        return None
    return "\n".join(lines[start - 1 : min(end, len(lines))])


# Shapes an agent must know to write correct code (what fields does this
# have, what variants does this enum allow) are worth inlining. Behaviour
# usually is not: a function's body is what the agent is about to reason
# about, and it can Read exactly that range if it needs to.
_SHAPE_KINDS = frozenset({"class", "enum", "struct", "interface", "const"})


def _use_cards(
    uses: list[dict],
    root: Path | None,
    sibling_qnames: set[str],
    budget: int,
) -> list[Card]:
    """Build the USES list, inlining only where inlining genuinely pays.

    Three rules, in order:
      - never inline a sibling already named under DEFINED IN, or a member of
        something else in this list -- that is the same fact twice;
      - prefer shapes (types, enums, constants) over behaviour;
      - stop once inlining has eaten its share of the budget, so a symbol with
        many small dependencies cannot quietly fill the response with source.
    """
    inline_budget = int(budget * 0.30)
    spent = 0
    qnames = {row["qname"] for row in uses}

    # Shapes only. A function body is the thing the agent is about to reason
    # about and it can Read that exact range; a type's shape is a fact it
    # needs merely to write a correct call, and pointing at it would cost
    # more than stating it.
    ranked = sorted(
        (r for r in uses if r["kind"] in _SHAPE_KINDS),
        key=lambda r: (r["end_line"] or 0) - (r["start_line"] or 0),
    )
    inlined: dict[str, str] = {}
    for row in ranked:
        span = (row["end_line"] or 0) - (row["start_line"] or 0) + 1
        if not 0 < span <= INLINE_MAX_LINES:
            continue
        if row["qname"] in sibling_qnames:
            continue
        parent = row["qname"].rsplit(".", 1)[0]
        if parent in qnames and parent != row["qname"]:
            continue        # its container is already in this list
        body = _read_lines(root, row["path"], row["start_line"], row["end_line"])
        if body is None:
            continue
        cost = estimate_tokens(body)
        if spent + cost > inline_budget:
            continue
        inlined[row["qname"]] = body
        spent += cost

    cards = []
    for row in sorted(uses, key=lambda r: (r["path"], r["start_line"] or 0)):
        body = inlined.get(row["qname"])
        note = ", ".join(sorted(v for v in row["vias"] if v))
        if row["qname"] in sibling_qnames:
            note = f"{note} | sibling, see DEFINED IN" if note else "sibling"
        cards.append(Card(
            qname=row["qname"], path=row["path"],
            start_line=row["start_line"], end_line=row["end_line"],
            kind=row["kind"], signature="" if body else row["signature"],
            reason=note, inline_body=body, score=1.0,
        ))
    return cards


def _find_symbol(repo: str, qname: str) -> dict | None:
    rows = db.read(
        """
        MATCH (s:Symbol {repo: $repo})
        WHERE s.qname = $qname OR s.qname ENDS WITH '.' + $qname OR s.name = $qname
        RETURN s.qname AS qname, s.name AS name, s.kind AS kind, s.path AS path,
               s.signature AS signature, s.docstring AS docstring,
               s.start_line AS start_line, s.end_line AS end_line,
               s.parent AS parent, s.is_test AS is_test
        ORDER BY size(s.qname) LIMIT 1
        """,
        repo=repo, qname=qname,
    )
    return rows[0] if rows else None


def symbol_context(
    repo: str, qname: str, budget_tokens: int | None = None
) -> Pack:
    """Everything needed to change one symbol safely, in one response."""
    budget = budget_tokens or BUDGET_SYMBOL_CONTEXT

    target = _find_symbol(repo, qname)
    if target is None:
        pack = Pack(title=f"SYMBOL CONTEXT  {qname}", budget_tokens=budget)
        pack.notes.append(f"no symbol matching '{qname}' in repo '{repo}'")
        return pack

    root = _repo_root(repo)
    pack = Pack(title=f"SYMBOL CONTEXT  {target['qname']}", budget_tokens=budget)

    # --- TARGET -----------------------------------------------------------
    pack.sections.append(Section("TARGET", [Card(
        qname=target["qname"], path=target["path"],
        start_line=target["start_line"], end_line=target["end_line"],
        kind=target["kind"], signature=target["signature"],
        reason=target["docstring"].splitlines()[0][:120] if target["docstring"] else "",
        score=1.0,
    )]))

    # --- DEFINED IN: the enclosing class and its other methods -------------
    sibling_qnames: set[str] = set()
    if target["parent"]:
        rows = db.read(
            """
            MATCH (cls:Symbol {repo: $repo})-[:DEFINES]->(t:Symbol {qname: $qname})
            OPTIONAL MATCH (cls)-[:DEFINES]->(sib:Symbol)
            WHERE sib.qname <> $qname
            RETURN cls.qname AS cls, cls.path AS path, cls.start_line AS start_line,
                   cls.end_line AS end_line, cls.signature AS signature,
                   collect(DISTINCT sib.name)[0..12] AS siblings,
                   collect(DISTINCT sib.qname) AS sibling_qnames
            """,
            repo=repo, qname=target["qname"],
        )
        if rows and rows[0]["cls"]:
            row = rows[0]
            sibling_qnames = {q for q in row["sibling_qnames"] if q} | {row["cls"]}
            siblings = " | ".join(f"{n}()" for n in row["siblings"] if n)
            pack.sections.append(Section("DEFINED IN", [Card(
                qname=row["cls"], path=row["path"],
                start_line=row["start_line"], end_line=row["end_line"],
                signature=row["signature"],
                placement=f"siblings: {siblings}" if siblings else "",
                score=1.0,
            )]))

    # --- USES: what this depends on, inward -------------------------------
    uses = db.read(
        """
        MATCH (t:Symbol {repo: $repo, qname: $qname})-[r:CALLS|REFERENCES]->(d:Symbol)
        RETURN DISTINCT d.qname AS qname, d.name AS name, d.kind AS kind,
               d.path AS path, d.signature AS signature,
               d.start_line AS start_line, d.end_line AS end_line,
               collect(DISTINCT coalesce(r.via, 'call')) AS vias
        ORDER BY d.path, d.start_line
        """,
        repo=repo, qname=target["qname"],
    )
    if uses:
        pack.sections.append(Section("USES", _use_cards(
            uses, root, sibling_qnames, budget,
        )))

    # --- CALLED BY: what depends on this, outward -------------------------
    callers = db.read(
        """
        MATCH (c:Symbol {repo: $repo})-[:CALLS]->(t:Symbol {qname: $qname})
        RETURN DISTINCT c.qname AS qname, c.path AS path, c.signature AS signature,
               c.start_line AS start_line, c.end_line AS end_line,
               coalesce(c.is_test, false) AS is_test
        ORDER BY c.path
        """,
        repo=repo, qname=target["qname"],
    )
    non_test_callers = [r for r in callers if not r["is_test"]]
    if non_test_callers:
        pack.sections.append(Section("CALLED BY", [
            Card(qname=r["qname"], path=r["path"], start_line=r["start_line"],
                 end_line=r["end_line"], signature="", score=1.0)
            for r in non_test_callers
        ]))

    # --- TESTED BY --------------------------------------------------------
    tests = db.read(
        """
        MATCH (t:Symbol {repo: $repo, qname: $qname})-[r:TESTED_BY]->(test:Symbol)
        WHERE r.confidence IN ['high', 'medium']
        RETURN test.qname AS qname, test.path AS path, test.start_line AS start_line,
               test.end_line AS end_line, r.confidence AS confidence
        ORDER BY r.confidence, test.qname
        """,
        repo=repo, qname=target["qname"],
    )
    if tests:
        pack.sections.append(Section("TESTED BY", [
            Card(qname=r["qname"], path=r["path"], start_line=r["start_line"],
                 end_line=r["end_line"], reason=f"{r['confidence']} confidence", score=1.0)
            for r in tests
        ]))
    else:
        pack.sections.append(Section("TESTED BY", [], note="no covering tests found"))

    # --- CO-CHANGES: file-level, projected onto the symbol ----------------
    cochange = db.read(
        """
        MATCH (t:Symbol {repo: $repo, qname: $qname})<-[:DEFINES]-(f:File)
        MATCH (f)-[r:CO_CHANGED]-(other:File)
        RETURN other.path AS path, r.count AS count, r.last_seen AS last_seen
        ORDER BY r.weight DESC LIMIT 5
        """,
        repo=repo, qname=target["qname"],
    )
    if cochange:
        pack.sections.append(Section("CO-CHANGES", [
            Card(qname="", path=r["path"], start_line=0,
                 reason=f"{r['count']}x, last {r['last_seen']}", score=1.0)
            for r in cochange
        ]))

    if target.get("is_test"):
        pack.notes.append("this symbol is test code")
    _note_untyped(repo, target["path"], pack)
    return pack


def _note_untyped(repo: str, path: str, pack: Pack) -> None:
    """Admit when the USES list cannot be complete."""
    rows = db.read(
        "MATCH (f:File {uid: $uid}) RETURN f.lang AS lang",
        uid=f"{repo}:{path}",
    )
    if rows and rows[0]["lang"] in ("javascript",):
        pack.notes.append("types unresolved (untyped source): USES lists calls only")


def what_breaks(
    repo: str, qname: str, depth: int = 2, budget_tokens: int | None = None
) -> Pack:
    """Blast radius: transitive callers, covering tests, and co-changed files."""
    budget = budget_tokens or BUDGET_WHAT_BREAKS

    target = _find_symbol(repo, qname)
    if target is None:
        pack = Pack(title=f"WHAT BREAKS  {qname}", budget_tokens=budget)
        pack.notes.append(f"no symbol matching '{qname}' in repo '{repo}'")
        return pack

    depth = max(1, min(depth, 4))
    pack = Pack(title=f"WHAT BREAKS  {target['qname']}", budget_tokens=budget)

    rows = db.read(
        f"""
        MATCH path = (c:Symbol {{repo: $repo}})-[:CALLS*1..{depth}]->(t:Symbol {{qname: $qname}})
        WITH c, min(length(path)) AS hops
        RETURN c.qname AS qname, c.path AS path, c.signature AS signature,
               c.start_line AS start_line, c.end_line AS end_line,
               coalesce(c.is_test, false) AS is_test, hops
        ORDER BY hops, c.path
        """,
        repo=repo, qname=target["qname"],
    )
    direct = [r for r in rows if not r["is_test"]]
    if direct:
        pack.sections.append(Section(
            f"CALLERS (up to {depth} hops)",
            collapse_by_file([
                Card(qname=r["qname"], path=r["path"], start_line=r["start_line"],
                     end_line=r["end_line"], signature="",
                     reason=f"{r['hops']} hop" + ("s" if r["hops"] > 1 else ""),
                     score=1.0 / r["hops"])
                for r in direct
            ]),
        ))
    else:
        pack.sections.append(Section("CALLERS", [], note="none - nothing calls this"))

    tests = db.read(
        """
        MATCH (t:Symbol {repo: $repo, qname: $qname})-[r:TESTED_BY]->(test:Symbol)
        RETURN test.qname AS qname, test.path AS path, test.start_line AS start_line,
               r.confidence AS confidence
        ORDER BY r.confidence
        """,
        repo=repo, qname=target["qname"],
    )
    pack.sections.append(Section(
        "TESTS THAT WOULD RUN",
        [Card(qname=r["qname"], path=r["path"], start_line=r["start_line"],
              reason=r["confidence"], score=1.0) for r in tests],
        note="" if tests else "none - this change is unguarded by tests",
    ))

    cochange = db.read(
        """
        MATCH (t:Symbol {repo: $repo, qname: $qname})<-[:DEFINES]-(f:File)
        MATCH (f)-[r:CO_CHANGED]-(other:File)
        RETURN other.path AS path, r.count AS count, r.last_seen AS last_seen
        ORDER BY r.weight DESC LIMIT 8
        """,
        repo=repo, qname=target["qname"],
    )
    if cochange:
        pack.sections.append(Section(
            "ALSO USUALLY CHANGED",
            [Card(qname="", path=r["path"], start_line=0,
                  reason=f"changed together {r['count']}x, last {r['last_seen']}", score=1.0)
             for r in cochange],
            note="history-derived; no import or call may exist between these",
        ))
    else:
        has_history = db.read(
            "MATCH (r:Repo {name: $repo}) RETURN coalesce(r.has_history, false) AS h",
            repo=repo,
        )
        if has_history and not has_history[0]["h"]:
            pack.notes.append("no git history: co-change unavailable")

    return pack


def what_tests(repo: str, qname: str, budget_tokens: int | None = None) -> Pack:
    """Which tests cover a symbol, strongest evidence first."""
    target = _find_symbol(repo, qname)
    pack = Pack(
        title=f"TESTS COVERING  {target['qname'] if target else qname}",
        budget_tokens=budget_tokens or BUDGET_SYMBOL_CONTEXT,
    )
    if target is None:
        pack.notes.append(f"no symbol matching '{qname}' in repo '{repo}'")
        return pack

    rows = db.read(
        """
        MATCH (t:Symbol {repo: $repo, qname: $qname})-[r:TESTED_BY]->(test:Symbol)
        RETURN test.qname AS qname, test.path AS path, test.start_line AS start_line,
               test.end_line AS end_line, r.confidence AS confidence
        ORDER BY CASE r.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
        """,
        repo=repo, qname=target["qname"],
    )
    pack.sections.append(Section("", [
        Card(qname=r["qname"], path=r["path"], start_line=r["start_line"],
             end_line=r["end_line"], reason=f"{r['confidence']} confidence", score=1.0)
        for r in rows
    ], note="" if rows else "no covering tests found"))
    return pack


def who_calls(
    repo: str, qname: str, depth: int = 2, budget_tokens: int | None = None
) -> Pack:
    """Inbound call tree."""
    target = _find_symbol(repo, qname)
    pack = Pack(
        title=f"WHO CALLS  {target['qname'] if target else qname}",
        budget_tokens=budget_tokens or BUDGET_WHAT_BREAKS,
    )
    if target is None:
        pack.notes.append(f"no symbol matching '{qname}' in repo '{repo}'")
        return pack

    depth = max(1, min(depth, 4))
    rows = db.read(
        f"""
        MATCH path = (c:Symbol {{repo: $repo}})-[:CALLS*1..{depth}]->(t:Symbol {{qname: $qname}})
        WITH c, min(length(path)) AS hops
        RETURN c.qname AS qname, c.path AS path, c.start_line AS start_line,
               c.end_line AS end_line, hops
        ORDER BY hops, c.path
        """,
        repo=repo, qname=target["qname"],
    )
    pack.sections.append(Section("", collapse_by_file([
        Card(qname=r["qname"], path=r["path"], start_line=r["start_line"],
             end_line=r["end_line"],
             reason=f"{r['hops']} hop" + ("s" if r["hops"] > 1 else ""),
             score=1.0 / r["hops"])
        for r in rows
    ]), note="" if rows else "nothing calls this"))
    return pack


def file_context(repo: str, path: str, budget_tokens: int | None = None) -> Pack:
    """A file's outline: every symbol with signature and line range, no bodies.

    Reading a 3,000-line file costs tens of thousands of tokens. Its outline
    costs a few hundred, and is usually enough to decide which part to read.
    """
    budget = budget_tokens or BUDGET_FILE_CONTEXT

    rows = db.read(
        """
        MATCH (f:File {repo: $repo})
        WHERE f.path = $path OR f.path ENDS WITH $path
        OPTIONAL MATCH (f)-[:DEFINES]->(s:Symbol)
        RETURN f.path AS path, f.lang AS lang, f.loc AS loc,
               collect({qname: s.qname, name: s.name, kind: s.kind,
                        signature: s.signature, start_line: s.start_line,
                        end_line: s.end_line, parent: s.parent}) AS symbols
        LIMIT 1
        """,
        repo=repo, path=path,
    )
    if not rows or not rows[0]["path"]:
        pack = Pack(title=f"FILE  {path}", budget_tokens=budget)
        pack.notes.append(f"'{path}' is not indexed under repo '{repo}'")
        return pack

    row = rows[0]
    pack = Pack(
        title=f"FILE  {row['path']}  ({row['lang']}, {row['loc']} lines)",
        budget_tokens=budget,
    )
    symbols = [s for s in row["symbols"] if s.get("qname")]
    symbols.sort(key=lambda s: s["start_line"] or 0)
    pack.sections.append(Section("OUTLINE", [
        Card(qname=s["qname"], path=row["path"], start_line=s["start_line"],
             end_line=s["end_line"], kind=s["kind"], signature=s["signature"],
             score=1.0)
        for s in symbols
    ], note="" if symbols else "no symbols (config or data file)"))

    importers = db.read(
        """
        MATCH (other:File {repo: $repo})-[:IMPORTS]->(f:File {uid: $uid})
        RETURN other.path AS path ORDER BY other.path LIMIT 10
        """,
        repo=repo, uid=f"{repo}:{row['path']}",
    )
    if importers:
        pack.sections.append(Section("IMPORTED BY", [
            Card(qname="", path=r["path"], start_line=0, score=1.0) for r in importers
        ]))

    cochange = db.read(
        """
        MATCH (f:File {uid: $uid})-[r:CO_CHANGED]-(other:File)
        RETURN other.path AS path, r.count AS count
        ORDER BY r.weight DESC LIMIT 5
        """,
        uid=f"{repo}:{row['path']}",
    )
    if cochange:
        pack.sections.append(Section("CO-CHANGES", [
            Card(qname="", path=r["path"], start_line=0,
                 reason=f"{r['count']}x", score=1.0)
            for r in cochange
        ]))
    return pack
