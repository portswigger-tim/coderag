# coderag

A context-economy engine for agentic work on large codebases.

An agent dropped into an unfamiliar repo greps, gets two hundred matches, reads eight whole
files, burns 40k tokens, and leaves most of that irrelevant material in the window for the rest
of the session. The cost is not only tokens: polluted context degrades every later turn.

coderag indexes a source tree into Neo4j as **both** a vector store and a code graph, and exposes
it to Claude Code over MCP. It answers with **pointers and shapes**, not source dumps: a symbol's
signature, its `path:line` range, and why it was selected. The agent reads only the ranges it
actually needs.

The number that matters is therefore **tokens to a correct answer**, not recall.

## What it costs to answer a question

Measured against the naive path an agent would otherwise take — grep, then open the four most
promising files:

| corpus | median token saving |
|---|---|
| `rich` (100 files, 38k lines, real library) | **82×** |
| bundled sample (12 files, one language) | 4× |

The saving scales with the repo, which is the point — the bundled sample understates it by more
than an order of magnitude because grep is cheap when there are only twelve files to grep. Run
`coderag eval` for the sample table; the `rich` figures come from indexing a package already in
the virtualenv, so they are reproducible without a network.

Correctness is scored alongside cost. A tool can always be made cheaper by returning less;
`expect_symbols` and `must_contain` assertions in `eval/golden.yaml` are what stop that from
looking like an improvement.

## Quick start

```bash
docker compose up -d                        # Neo4j 5.26 with the vector index
uv run python scripts/make_sample_history.py   # build the sample repo with real git history
uv run coderag demo                         # index all five language samples, then score them
```

Then point it at something real:

```bash
uv run coderag index ~/code/my-project --repo my-project
uv run coderag search "how is rate limiting applied" --repo my-project
```

No API keys. Embeddings run locally on CPU (`BAAI/bge-small-en-v1.5`, ~130 MB, downloaded once).

## Using it from Claude Code

```bash
claude mcp add coderag -- uv run --directory "$PWD" coderag-mcp
```

Or use the committed `.mcp.json`. With one repo indexed the tools find it themselves; set
`CODERAG_REPO` when the database holds several and you want a default.

The server exposes seven tools, and its instructions state the intended sequence so the model
does not have to infer one:

| tool | what it is for |
|---|---|
| `search_code` | find where something lives |
| `symbol_context` | **everything needed to change one symbol safely** |
| `what_breaks` | blast radius: callers, tests, co-changed files |
| `what_tests` | which tests cover this |
| `who_calls` | inbound call tree |
| `file_context` | a file's outline — signatures and line ranges, no bodies |
| `index_status` | what is indexed, and how much of it resolved |

`file_context` is the quiet win: a 3,000-line file costs tens of thousands of tokens to read and
a few hundred to outline.

### The flagship: `symbol_context`

```
SYMBOL CONTEXT  services.pricing.PricingService.apply_bulk_discount

TARGET
services.pricing.PricingService.apply_bulk_discount
  def apply_bulk_discount(self, cart: Cart, tier: Tier) -> Money:
  services/pricing.py:38-54

DEFINED IN
services.pricing.PricingService
  services/pricing.py:28-63
  <- siblings: base_price() | _round() | apply_coupon()

USES
db.models.Tier
  db/models.py:11-16
  <- param
    class Tier(enum.Enum):
        BRONZE = "bronze"
        SILVER = "silver"
        GOLD = "gold"
...

CALLED BY        api.admin.recalculate · order_service.OrderService.place_order
TESTED BY        tests/test_pricing.py:22, :30
CO-CHANGES       config/rates.yaml   7x, last 2026-07-21
```

Roughly 650 tokens. Assembling the same understanding by reading four files costs about 8,000.

Small types are **inlined**; behaviour is not. A nine-line enum costs less to state than to point
at, while a function body is the thing the agent is about to reason about and can read exactly.

## Two edges static analysis cannot produce

**`CO_CHANGED`** — mined from `git log`. On a real 347-commit repo the strongest edges were
between a CI pipeline definition, a build file and a shell script: no import, no call,
different languages, and unmistakably coupled. In the sample it links `config/rates.yaml` to
`services/pricing.py`, which is the only way to answer *"if I change the discount thresholds,
what else needs updating?"*

Guarded against the obvious failure modes: merge commits excluded, sweeping commits capped at 25
files (a 400-file commit would otherwise emit ~80k spurious pairs), recency-decayed, minimum
support of 3, renames followed. Shallow clones and non-git trees are detected and reported rather
than silently producing nothing.

**`TESTED_BY`** — graded by evidence: `high` when a test imports and calls the symbol, `medium`
for a repo-unique call, `low` for a naming-convention match with no call observed. Only `high`
and `medium` surface by default.

## Languages

Python, TypeScript/TSX, JavaScript, Go, Java, Rust. Adding one means adding a tree-sitter query
file under `src/coderag/parsers/queries/` — no Python changes.

Config and data files (`.yaml`, `.toml`, `.json`, `.ini`, `.sql`) are indexed as searchable chunks
without symbols, because *"which config does this read?"* is a question agents ask constantly.

Jest/Mocha/Vitest `test("name", () => {…})` bodies are captured as named symbols. Without that,
every call inside a JS/TS suite has no enclosing definition and is discarded — which silently
costs `TESTED_BY` edges across most of that ecosystem.

## What the graph does, and what it does not

Honest accounting, because the measurements say something more specific than "graphs help":

- **It makes `symbol_context`, `what_breaks`, `what_tests` and `who_calls` possible at all.**
  None of these exist without traversable relationships. This is where the value is.
- **It contributes little to search ranking.** On the bundled sample, prune-and-boost changes
  recall not at all and costs ~60 tokens per query. Run `coderag eval --no-graph` and compare:
  the numbers are near-identical. Search quality here comes mostly from weighted hybrid retrieval,
  not from the graph.

### What `coderag eval` cannot tell you

The golden set scores retrieval against the bundled samples, and those samples are clean: no
licence headers, almost no grouped imports. So a chunking bug that only fires on real-world
boilerplate is invisible to it. That is not hypothetical — the licence-header defect scored
**16/16 both with the fix and with it deliberately reverted**, and was found instead by asking
an indexed 161-file Go repository a question. Chunking rules are therefore guarded by unit
tests in `tests/test_chunker.py`, which assert in both directions: boilerplate must not be
indexed, and the doc comments on types must be. Eval measures ranking quality; it does not
measure what is eligible to be ranked.

Two retrieval findings worth recording, since both were measured rather than assumed:

- **Import blocks make terrible chunks.** They name every domain type in a file without saying
  anything about behaviour, so they out-match the code they import and answer nothing. They stay
  in the chunk header for context; they are not chunks of their own.
- **BM25 over a prose question is mostly noise.** Lucene does not stem, so "persisted" never
  matches "persist", and the arm ends up ranking on whichever common word happens to recur. The
  lexical arm is therefore weighted by how identifier-like the query is: full weight when the
  query names something that exists, heavily reduced for prose.

## Running it on a large repository

Measured on a large private Java monorepo: ~25k indexable files, ~4M lines, tens of
thousands of commits.

Three things matter at that size, all of them learned the hard way:

**Embedding is the entire cost.** Profiling a 225-file module: walking 0.03s, parsing 0.08s,
chunking 0.01s, embedding 61s. Nothing else is worth optimising.

**Batch by length.** Transformer cost scales with the longest sequence in a batch, because
everything shorter is padded up to it — and code chunks range from two-line getters to 200-line
methods. Sorting by length before batching measured **2.5× faster** (30 → 75 chunks/sec on real
Java) with byte-identical output. This is done automatically.

**Neo4j's memory must fit the Docker VM, not the host.** Docker Desktop caps its VM at a few GB
regardless of machine RAM; heap + pagecache above that makes Neo4j exit at startup with "Invalid
memory configuration" rather than start degraded. Check `docker info | grep Memory` before
raising the values in `docker-compose.yml`.

## Configuration

Copy `.env.example` to `.env`. Defaults match `docker-compose.yml` and are local-only.

| variable | default | notes |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | |
| `CODERAG_REPO` | *(unset)* | MCP only: which repo to answer about when a call omits one |

That is the entire surface — one variable, plus an optional default for the MCP server.

**There is no username or password.** The bundled database runs with authentication disabled
(`NEO4J_AUTH: none`) and its ports bound to `127.0.0.1`, so it is unreachable from the network.
A credential that guards a loopback-only dev database is a credential to manage, not a control,
and the old `coderag-local` password was committed in three files anyway. The loopback binding
is now the thing keeping it private, which is why it is not optional: Docker publishes to every
interface unless told otherwise, and auth-off on `0.0.0.0` would expose the database to the
whole LAN. If you ever point `NEO4J_URI` at a database reachable from a network, enable
authentication there and restore the `auth=` argument in `db.py`.

Batch sizes, response budgets, co-change thresholds and the embedding model were all settings
once. Each was chosen by measurement, so each is now a constant next to the code that uses it —
a knob nobody tunes is a knob that ships wrong, and `CODERAG_EMBED_BATCH_SIZE` in particular
mostly invited people to make indexing slower (256 was 22% worse than 64). Response budgets
remain adjustable where it matters: per call, through the MCP tools' `budget_tokens`.

If `CODERAG_REPO` is unset, the tools use the only indexed repo, or name the candidates. The CLI
does the same, preferring the directory you are standing in.

### Why there is only one embedding model, and no way to select another

Nine candidates were measured, not assumed. 928 chunks of `rich` with 120 unbiased
docstring-to-function queries (CodeSearchNet protocol: docstrings stripped from the indexed text
and each symbol's own name stripped from its query, so nothing leaks):

| model | dim | chunks/sec | hit@1 | hit@5 | MRR |
|---|---|---|---|---|---|
| **`bge-small-en-v1.5`** | 384 | 25 | **0.792** | **0.950** | **0.859** |
| `all-MiniLM-L6-v2` | 384 | **296** | 0.733 | 0.933 | 0.814 |
| `jina-embeddings-v2-small-en` | 512 | 26 | 0.750 | 0.933 | 0.828 |
| `snowflake-arctic-embed-s` | 384 | 32 | 0.592 | 0.817 | 0.686 |
| `snowflake-arctic-embed-xs` | 384 | 64 | 0.558 | 0.792 | 0.658 |
| `jina-v2-base-code` | 768 | 2 | 0.725 | 0.883 | 0.798 |
| `nomic-embed-text-v1.5` | 768 | 1 | 0.692 | 0.908 | 0.788 |
| `nomic-embed-text-v1.5-Q` | 768 | 3 | 0.642 | 0.900 | 0.753 |

`bge-small` wins on quality outright. The code-specialised option is 12.5× slower *and* worse,
which is the second corpus to say so. Quantization does work — the two `nomic` rows are the same
weights in fp32 and int8, buying 3× throughput for 0.035 MRR — but the model it rescues is still
eight times too slow, and `bge-small` already ships as an optimised ONNX build
(`model_optimized.onnx`), so that win is banked. CoreML made no difference (24 vs 25 chunks/sec).

`all-MiniLM-L6-v2` is the one real speed option: 11.8× faster for 0.045 MRR. It is not offered,
for a reason that outlives the quality gap. It is also 384-dim, so it would share the single
`chunk_embedding` vector index with `bge-small` and Neo4j would accept both without complaint —
two vector spaces mixed in one index, producing meaningless similarity with no error anywhere.
The dimension is the only thing that check rests on, and here it matches. A selectable embedder
is therefore not a feature with a caveat; it is a corruption vector. It also truncates at 128
tokens, discarding ~44% of the indexed text on this corpus.

So there is no setting, no environment variable and no argument that selects a model:
`get_embedder()` takes nothing, and `MODEL_ID` is the single source of truth. `:Repo` records
that id, so `coderag stats` and `index_status` name the exact model behind the vectors.

Re-run the comparison before reintroducing any option; do not add one on reputation.

## Limitations

- **Call resolution is heuristic, not a compiler.** Import-scoped name matching, never crossing a
  language boundary. Ambiguity is recorded as unresolved rather than guessed; `coderag stats`
  reports the ratio (0% on the sample, ~16% on `rich`). Dynamic dispatch and reflection are
  invisible.
- **Co-change is file-level.** Symbol-level would need `git log -L` per symbol, which is far too
  slow. Symbols inherit it by projecting through `DEFINES`.
- **Indexing a multi-million-line repository takes tens of minutes**, essentially all of it
  embedding. Scope it with `--only <subdir>` for a first pass.
- **Token counts are estimates** (`chars/4` with a conservative margin). Exact counting would mean
  either shipping the wrong tokenizer or calling an API, and the second breaks the no-key promise.
- **Re-indexing is cheap; treat it as the normal operation.** Unchanged files are skipped by
  content hash, but there is no mid-run resumption — an interrupted index is simply re-run.
- **The Rust sample is parser-verified only.** No cargo toolchain was available here, so unlike
  the Python, Go and Java samples it has not been compiled or executed.

## Layout

```
src/coderag/
  walker.py     discovery, language detection, test detection
  parsers/      tree-sitter extraction, one .scm per language
  chunker.py    symbol-aware chunking with context headers
  embedder.py   local embedding backends, length-sorted batching
  resolver.py   repo-wide name binding
  testlink.py   TESTED_BY derivation
  gitmine.py    CO_CHANGED derivation
  indexer.py    orchestration
  retriever.py  weighted hybrid search plus the graph pass
  context.py    symbol_context, what_breaks, what_tests, file_context
  pack.py       the response contract: budgets, collapsing, truncation
  mcp_server.py MCP stdio server
  eval.py       token-cost harness
samples/        one implementation per language, plus a scripted git history
```

## Development

```bash
uv sync
uv run pytest                 # 40 tests, no database required
uv run coderag eval           # scored against the sample
uv run coderag eval --no-graph
```
