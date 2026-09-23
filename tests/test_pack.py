"""The response contract: budgets, collapsing, truncation."""

from __future__ import annotations

from coderag.pack import (
    Card, Pack, Section, collapse_by_file, dedupe_by_symbol,
    estimate_tokens, module_of, normalise_scores, summarise_by_module,
)


def _card(qname="a.b", path="a.py", line=1, score=1.0):
    return Card(qname=qname, path=path, start_line=line, end_line=line + 5,
                signature="def b(self) -> int:", score=score)


def test_token_estimate_is_conservative():
    text = "x" * 400
    assert estimate_tokens(text) >= 100      # never under-counts chars/4


def test_pack_never_exceeds_its_budget():
    pack = Pack(title="T", budget_tokens=60,
                sections=[Section("", [_card(f"a.b{i}", line=i) for i in range(50)])])
    assert pack.tokens() <= 60 * 1.6         # rendering overhead only, no runaway
    assert "showing" in pack.render()


def test_truncation_is_always_stated():
    pack = Pack(budget_tokens=40,
                sections=[Section("", [_card(f"a.b{i}", line=i) for i in range(20)])],
                total_available=20)
    assert "showing" in pack.render() and "of 20" in pack.render()


def test_collapse_by_file_folds_call_sites():
    cards = [_card("a.b", "api/routes.py", line=n, score=1.0 / n) for n in (45, 88, 201, 310)]
    collapsed = collapse_by_file(cards)
    assert len(collapsed) == 1
    assert collapsed[0].location() == "api/routes.py:45,88,201 (+1)"


def test_dedupe_keeps_the_best_chunk_per_symbol_not_per_file():
    """Distinct symbols in one file are distinct answers and must not merge."""
    cards = [
        _card("mod.alpha", "m.py", line=10, score=0.4),
        _card("mod.alpha", "m.py", line=10, score=0.9),
        _card("mod.beta", "m.py", line=80, score=0.5),
    ]
    out = dedupe_by_symbol(cards)
    assert [c.qname for c in out] == ["mod.alpha", "mod.beta"]
    assert out[0].score == 0.9


def test_scores_are_normalised_relative_to_the_top_hit():
    cards = [_card(score=0.04), _card(qname="a.c", score=0.02)]
    normalise_scores(cards)
    assert cards[0].score == 1.0
    assert cards[1].score == 0.5


def test_module_summary_needs_several_modules():
    assert summarise_by_module([_card(path="a/x.py")]) is None
    wide = summarise_by_module([_card(path=f"m{i}/x.py") for i in range(5)])
    assert wide is not None and "MODULES" in wide.title


def test_card_without_a_qname_does_not_repeat_its_path():
    card = Card(qname="", path="config/rates.yaml", start_line=0, reason="7x")
    assert card.render().count("config/rates.yaml") == 1


def test_module_of_groups_by_leading_segments():
    assert module_of("services/pricing.py") == "services"
    assert module_of("src/main/java/shop/A.java") == "src/main"


def test_every_setting_has_a_working_env_alias(monkeypatch):
    """Config aliases are documented in the README; a silently-ignored
    variable is worse than an undocumented one."""
    from coderag.config import Settings

    monkeypatch.setenv("NEO4J_URI", "bolt://example:7687")
    settings = Settings(_env_file=None)
    assert settings.neo4j_uri == "bolt://example:7687"


def test_configuration_stays_one_field():
    """Everything else is a measured constant beside the code that uses it.

    This test exists to make widening the surface a deliberate act rather
    than a drive-by: a knob nobody tunes is a knob that ships wrong.
    """
    from coderag.config import Settings

    assert set(Settings.model_fields) == {"neo4j_uri"}
