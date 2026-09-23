"""Parser behaviour, per language, with no database involved."""

from __future__ import annotations

import pytest

from coderag.parsers.treesitter import language_for_path, parse_source

PYTHON = b'''"""Module docs."""

from db.models import Cart


class Pricing:
    """Class docs."""

    def apply(self, cart: Cart) -> int:
        """Method docs."""
        return self.base(cart)

    def base(self, cart: Cart) -> int:
        return 0
'''


def test_python_symbols_kinds_and_parents():
    parsed = parse_source("services/pricing.py", PYTHON, "python")
    kinds = {s.local_qname: s.kind for s in parsed.symbols}
    assert kinds["Pricing"] == "class"
    assert kinds["Pricing.apply"] == "method"
    assert parsed.module_docstring.startswith("Module docs")


def test_python_docstrings_survive_both_grammar_shapes():
    parsed = parse_source("p.py", PYTHON, "python")
    apply_sym = next(s for s in parsed.symbols if s.name == "apply")
    assert apply_sym.docstring.startswith("Method docs")


def test_python_reference_vias():
    parsed = parse_source("p.py", PYTHON, "python")
    vias = {(r.from_local_qname, r.target_name): r.via for r in parsed.references}
    assert vias[("Pricing.apply", "Cart")] == "param"
    assert vias[("Pricing.apply", "base")] == "call"


def test_references_attribute_by_byte_span_not_line():
    """Several definitions on one line must not steal each other's references."""
    src = b'class Pricing extends Base { run() { return apply(this.cart); } }\n'
    parsed = parse_source("x.js", src, "javascript")
    pairs = {(r.from_local_qname, r.target_name) for r in parsed.references}
    assert ("Pricing", "Base") in pairs          # inheritance belongs to the class
    assert ("Pricing.run", "apply") in pairs     # the call belongs to the method


@pytest.mark.parametrize(
    ("lang", "source", "expected"),
    [
        ("go", b'package p\nfunc Apply(c *Cart) int { return compute(c) }\n', "Apply"),
        ("java", b'package p;\npublic class A { public int go(B b) { return 1; } }\n', "A.go"),
        ("rust", b'pub fn apply(cart: &Cart) -> i32 { compute(cart) }\n', "apply"),
        ("typescript", b'export function apply(c: Cart): number { return 1; }\n', "apply"),
    ],
)
def test_every_language_extracts_definitions(lang, source, expected):
    parsed = parse_source(f"x.{lang}", source, lang)
    assert expected in {s.local_qname for s in parsed.symbols}


def test_jest_style_tests_become_symbols():
    """Anonymous callbacks would otherwise discard every call inside a suite."""
    src = b'test("does a thing", () => { expect(apply(1)).toBe(2); });\n'
    parsed = parse_source("x.test.ts", src, "typescript")
    assert "does a thing" in {s.local_qname for s in parsed.symbols}
    assert ("does a thing", "apply") in {
        (r.from_local_qname, r.target_name) for r in parsed.references
    }


def test_go_import_paths_lose_their_quotes():
    parsed = parse_source("x.go", b'package p\nimport "fmt"\n', "go")
    assert [i.module for i in parsed.imports] == ["fmt"]


def test_language_detection():
    assert language_for_path("a/b.py") == "python"
    assert language_for_path("a/b.rs") == "rust"
    assert language_for_path("a/b.md") is None
