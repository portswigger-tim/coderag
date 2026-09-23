"""The response contract.

Every tool returns cards under a token budget, never raw source dumps. This
module owns estimation, collapsing, truncation and rendering so no individual
tool can quietly flood the caller's context.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import PurePosixPath

# Tokens are estimated, not counted. An exact count needs a tokenizer we would
# have to either ship (wrong tokenizer for the consuming model) or call an API
# for (breaks the no-key promise). chars/4 is the standard approximation for
# code and prose alike; the margin below makes the estimate conservative so a
# budget is met rather than merely approached.
_CHARS_PER_TOKEN = 4.0
_SAFETY_MARGIN = 1.15


def estimate_tokens(text: str) -> int:
    """Conservative token estimate. Deliberately over- rather than under-counts."""
    return math.ceil(len(text) / _CHARS_PER_TOKEN * _SAFETY_MARGIN)


def module_of(path: str) -> str:
    """Coarse grouping key for hierarchical fallback: the first two segments."""
    parts = PurePosixPath(path).parts
    return "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if parts else path)


@dataclass(slots=True)
class Card:
    """One result. Points at code; does not reproduce it unless inlining wins."""

    qname: str
    path: str
    start_line: int
    end_line: int = 0
    kind: str = ""
    signature: str = ""
    reason: str = ""
    placement: str = ""          # "in class PricingService", "called by X"
    score: float = 0.0
    extra_lines: list[int] = field(default_factory=list)   # collapsed call sites
    hidden_count: int = 0        # further sites in this file, not listed
    inline_body: str | None = None

    def location(self) -> str:
        if self.start_line == 0:
            return self.path          # module-altitude card, no line to point at
        if self.extra_lines:
            shown = ",".join(str(n) for n in [self.start_line, *self.extra_lines])
            tail = f" (+{self.hidden_count})" if self.hidden_count else ""
            return f"{self.path}:{shown}{tail}"
        if self.end_line and self.end_line != self.start_line:
            return f"{self.path}:{self.start_line}-{self.end_line}"
        return f"{self.path}:{self.start_line}"

    def render(self) -> str:
        titled = bool(self.qname)
        lines = [self.qname if titled else self.location()]
        if self.signature:
            lines.append(f"  {self.signature}")
        if titled:
            lines.append(f"  {self.location()}")
        bits = [b for b in (self.reason, self.placement) if b]
        if bits:
            lines.append(f"  <- {' | '.join(bits)}")
        if self.inline_body:
            body = "\n".join(f"    {ln}" for ln in self.inline_body.splitlines())
            lines.append(body)
        return "\n".join(lines)

    def tokens(self) -> int:
        return estimate_tokens(self.render())


@dataclass(slots=True)
class Section:
    """A labelled group of cards inside a pack (USES, CALLED BY, ...)."""

    title: str
    cards: list[Card] = field(default_factory=list)
    note: str = ""


@dataclass(slots=True)
class Pack:
    """A budgeted response. Truncation is always stated, never silent."""

    title: str = ""
    sections: list[Section] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    budget_tokens: int = 1500
    total_available: int | None = None   # for "showing N of M"

    def render(self) -> str:
        out: list[str] = []
        if self.title:
            out.append(self.title)
            out.append("")

        spent = estimate_tokens("\n".join(out))
        shown = 0
        total = sum(len(s.cards) for s in self.sections)
        truncated = False

        for section in self.sections:
            if not section.cards and not section.note:
                continue
            header = f"{section.title}" if section.title else ""
            header_cost = estimate_tokens(header) + 2
            if spent + header_cost > self.budget_tokens:
                truncated = True
                break
            if header:
                out.append(header)
                spent += header_cost

            for card in section.cards:
                cost = card.tokens()
                if spent + cost > self.budget_tokens:
                    truncated = True
                    break
                out.append(card.render())
                spent += cost
                shown += 1
            if section.note:
                out.append(f"  {section.note}")
                spent += estimate_tokens(section.note)
            out.append("")
            if truncated:
                break

        available = self.total_available if self.total_available is not None else total
        if truncated or shown < available:
            out.append(
                f"[showing {shown} of {available}"
                + (" - narrow the query, or raise budget_tokens, to see more"
                   if shown < available else "")
                + "]"
            )
        for note in self.notes:
            out.append(f"[{note}]")

        return "\n".join(out).rstrip() + "\n"

    def tokens(self) -> int:
        return estimate_tokens(self.render())


def dedupe_by_symbol(cards: list[Card]) -> list[Card]:
    """Keep the best-scoring card per symbol.

    A long function is split across several chunks, so the same symbol can
    match more than once. That is one answer, not three. Distinct symbols are
    never merged, even when they share a file -- they are distinct answers.
    """
    best: dict[str, Card] = {}
    for card in cards:
        key = card.qname or f"{card.path}:{card.start_line}"
        current = best.get(key)
        if current is None or card.score > current.score:
            best[key] = card
    return sorted(best.values(), key=lambda c: -c.score)


def normalise_scores(cards: list[Card]) -> None:
    """Rewrite raw fusion scores as a 0-1 relevance relative to the top hit.

    Reciprocal-rank-fusion values (0.03, 0.04) carry no meaning for a reader
    deciding which result to open; relative confidence does.
    """
    if not cards:
        return
    top = max(card.score for card in cards) or 1.0
    for card in cards:
        card.score = card.score / top


def collapse_by_file(cards: list[Card], max_per_file: int = 3) -> list[Card]:
    """Fold repeated *call sites* in one file into a single card.

    For call lists only: twelve call sites in one file is one fact, not
    twelve. Never use this on search results, where same-file cards are
    different symbols and merging them would misattribute line numbers.
    """
    by_path: dict[str, list[Card]] = {}
    for card in cards:
        by_path.setdefault(card.path, []).append(card)

    out: list[Card] = []
    for path, group in by_path.items():
        group.sort(key=lambda c: -c.score)
        if len(group) == 1:
            out.append(group[0])
            continue
        head = group[0]
        rest = sorted(c.start_line for c in group[1:])
        head.extra_lines = rest[: max_per_file - 1]
        head.hidden_count = max(0, len(rest) - (max_per_file - 1))
        out.append(head)
    out.sort(key=lambda c: -c.score)
    return out


def summarise_by_module(cards: list[Card], min_modules: int = 3) -> Section | None:
    """Module-altitude summary, for when the cards themselves will not fit.

    Used as a fallback when listing individual symbols would blow the token
    budget: naming the modules and letting the caller narrow is cheaper and
    more honest than truncating an arbitrary two-thirds of the results.
    """
    modules: dict[str, int] = {}
    for card in cards:
        modules[module_of(card.path)] = modules.get(module_of(card.path), 0) + 1
    if len(modules) < min_modules:
        return None

    ranked = sorted(modules.items(), key=lambda kv: -kv[1])
    section = Section(title=f"MATCHES SPAN {len(modules)} MODULES")
    for name, count in ranked[:10]:
        section.cards.append(
            Card(qname=name, path=name, start_line=0, reason=f"{count} matches")
        )
    section.note = "narrow with scope=<module> to see individual symbols"
    return section
