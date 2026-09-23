"""What is allowed to become a chunk, per language, with no database.

These exist because `coderag eval` cannot catch this class of bug. The
bundled samples carry no licence headers and almost no grouped imports, so
the corpus never exercises the pathology: eval scored 16/16 both with the
fix and with it deliberately reverted. The defect was found by asking a
real 161-file Go repository a question and getting six licence blocks back.

Two directions matter, and they pull against each other:

  - Boilerplate must not be indexed. A licence header repeated in every
    file is one near-duplicate vector per file, competing in every search
    and answering nothing.
  - Documentation must be. Types are not callables, so a Rust enum or a
    TypeScript interface never gets its own chunk -- it and its doc comment
    live in the leftover module chunk, and for a type that comment is
    frequently the only prose describing it.

An earlier fix satisfied the first and broke the second.
"""

from __future__ import annotations

import pytest

from coderag.chunker import chunk_file
from coderag.parsers.treesitter import parse_source

APACHE = """\
/*
Copyright 2025.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
*/
"""

GO = (APACHE + '''package controller

import (
	"context"
	"encoding/json"
	api "github.com/nats-io/nack/pkg/jetstream/apis/jetstream/v1beta2"
)

const (
	kvStreamPrefix = "KV_"
)

// KeyValueReconciler reconciles a KeyValue object.
type KeyValueReconciler struct {
	Scheme *runtime.Scheme
}

func (r *KeyValueReconciler) Reconcile(ctx context.Context) error {
	return nil
}
''').encode()

RUST = '''\
//! Domain entities shared across services and repositories.

use crate::money::Money;
use std::collections::{HashMap, BTreeSet};

/// Customer loyalty band. Multipliers live in the pricing module.
pub enum Tier {
    Bronze,
    Silver,
    Gold,
}

pub fn tier_multiplier(t: Tier) -> f64 {
    1.0
}
'''.encode()

TYPESCRIPT = '''\
// SPDX-License-Identifier: Apache-2.0

import {
  Money,
  Currency,
} from "./money";

/** A sellable item with an ISBN. */
export interface Book {
  isbn: string;
  unitPrice: Money;
}

export function totalQuantity(cart: Cart): number {
  return 0;
}
'''.encode()

CASES = {
    "go": (GO, "controller.go", "go"),
    "rust": (RUST, "models.rs", "rust"),
    "typescript": (TYPESCRIPT, "models.ts", "typescript"),
}


def module_text(source: bytes, path: str, lang: str) -> str:
    """Everything that ends up in this file's non-callable chunks."""
    parsed = parse_source(path, source, lang)
    chunks = chunk_file("r", parsed, source.decode())
    return "\n".join(c.text for c in chunks if c.kind == "module")


def all_text(source: bytes, path: str, lang: str) -> str:
    parsed = parse_source(path, source, lang)
    chunks = chunk_file("r", parsed, source.decode())
    return "\n".join(c.text for c in chunks)


@pytest.mark.parametrize("lang", sorted(CASES))
def test_licence_header_is_not_indexed(lang):
    """A per-file licence block is duplicate vocabulary, not content."""
    source, path, language = CASES[lang]
    text = all_text(source, path, language)
    for phrase in ("Copyright", "Licensed under", "SPDX-License"):
        assert phrase not in text, f"{lang}: licence text leaked into a chunk"


@pytest.mark.parametrize("lang", sorted(CASES))
def test_grouped_import_paths_are_not_indexed(lang):
    """Only the opening line of a grouped import carries a keyword.

    The paths inside are bare tokens that no prefix matches, which is how
    they used to survive into a module chunk.
    """
    source, path, language = CASES[lang]
    text = all_text(source, path, language)
    leaked = [p for p in ("encoding/json", "nats-io/nack", "BTreeSet", "Currency")
              if p in text]
    assert not leaked, f"{lang}: import paths leaked into a chunk: {leaked}"


def test_doc_comments_on_types_survive():
    """Types are not callables, so their only chunk is the module one.

    Stripping comments by syntax rather than position deletes these, and
    for a type the doc comment is often the only prose describing it.
    """
    assert "Customer loyalty band" in module_text(*CASES["rust"])
    assert "A sellable item" in module_text(*CASES["typescript"])
    assert "KeyValueReconciler reconciles" in module_text(*CASES["go"])


def test_declarations_survive():
    """Go's `const (` looks like a grouped import and is not one.

    A declared constant is an answer -- "what is the KV stream prefix?" --
    so the block stripper must key on the keyword, not on the bracket.
    """
    text = module_text(*CASES["go"])
    assert "kvStreamPrefix" in text
    assert "KV_" in text


def test_type_shapes_survive():
    """The fields are what "what does a Book look like?" is asking for."""
    assert "isbn" in module_text(*CASES["typescript"])
    assert "Bronze" in module_text(*CASES["rust"])


def test_callables_still_get_their_own_chunks():
    """None of the above may cost a function its chunk."""
    for lang, (source, path, language) in CASES.items():
        parsed = parse_source(path, source, language)
        chunks = chunk_file("r", parsed, source.decode())
        named = {c.symbol_qname for c in chunks if c.symbol_qname}
        assert named, f"{lang}: no callable chunks produced"
