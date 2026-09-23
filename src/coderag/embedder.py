"""Embedding, local and keyless.

One backend, and no way to select another. Alternatives were implemented and
removed, each measured rather than assumed: a hosted API backend (contradicted
the no-key promise), jina-embeddings-v2-base-code (3.6x the indexing time for
an identical MRR), and a survey of eight further models on 928 chunks of real
Python with 120 unbiased docstring-to-function queries. bge-small-en-v1.5 won
that survey outright on quality; the only faster option, all-MiniLM-L6-v2, ran
11.8x quicker for 0.045 lower MRR and truncates at 128 tokens, discarding ~44%
of the indexed text. There is deliberately no setting to reach it: a second
384-dim model would share the one vector index, and mixing two vector spaces
in it is silent corruption rather than an error.

Re-run the comparison before reintroducing any option; do not add one on
reputation.
"""

from __future__ import annotations

MODEL_ID = "BAAI/bge-small-en-v1.5"
DIM = 384

# fastembed forks worker processes per call, and each one loads its own copy
# of the model, so the fork cost is only amortised by a long batch. Measured
# on real chunks, 14-core M-series, serial vs eight workers:
#
#     texts/call    128    256    512    768   1024   1536   2048
#     speedup      0.55x  0.81x  1.11x  1.17x  1.22x  1.31x  1.26x
#
# Below ~512 parallelism costs more than it saves -- at 256 it is 19% slower
# -- so short batches stay in-process. End to end on 8,384 chunks this is
# 49 -> 63 chunks/sec, or 178s -> 141s of wall clock.
# Chunks per forward pass. 64 measured fastest; 256 was 22% slower, because
# a wider batch spans a wider length range and padding waste grows with it.
BATCH_SIZE = 64

PARALLEL_WORKERS = 8
PARALLEL_MIN_TEXTS = 512


class Embedder:
    """fastembed / ONNX on CPU. No API key, no network after first download."""

    def __init__(self, batch_size: int | None = None) -> None:
        # Recorded on :Repo and shown by `coderag stats` / index_status. It
        # is the model id, not a backend label: with one embedder a label
        # like "local" says nothing, while the id says exactly which model
        # produced the vectors in the index.
        self.name = MODEL_ID
        self.model_id = MODEL_ID
        self.dim = DIM
        self.batch_size = batch_size or BATCH_SIZE
        self._model = None   # loaded lazily so --help stays instant
        self._parallel_ok = True

    def _ensure(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_id)
        return self._model

    def warm(self) -> None:
        """Force the model download and load up front, with no query attached."""
        self._ensure()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, grouping texts of similar length together.

        Transformer cost scales with the longest sequence in a batch, because
        everything shorter is padded up to it. Code chunks vary enormously --
        a two-line getter beside a 200-line method -- so an unsorted batch
        pays the long chunk's price for every short one. Sorting first
        measured 2.5x faster on real Java, with byte-identical output.

        Long batches are then spread over PARALLEL_WORKERS processes, which
        measured a further 1.2x. Both are pure throughput changes: the
        vectors are identical either way.
        """
        if not texts:
            return []
        model = self._ensure()
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        ordered = [texts[i] for i in order]

        parallel = self._parallel_ok and len(ordered) >= PARALLEL_MIN_TEXTS
        try:
            raw = self._run(model, ordered, parallel)
        except (EOFError, OSError, RuntimeError):
            # Worker processes need an importable __main__ to re-enter, which
            # a caller running us from `python -c` or piped stdin does not
            # have; the failure surfaces as an EOFError deep inside
            # multiprocessing. Throughput is not worth a crash, so fall back
            # to in-process for the rest of this embedder's life.
            if not parallel:
                raise
            self._parallel_ok = False
            raw = self._run(model, ordered, parallel=False)

        vectors: list[list[float]] = [None] * len(texts)   # type: ignore[list-item]
        for position, vector in zip(order, raw, strict=True):
            vectors[position] = vector.tolist()
        return vectors

    def _run(self, model, ordered: list[str], parallel: bool) -> list:
        extra = {"parallel": PARALLEL_WORKERS} if parallel else {}
        return list(model.embed(ordered, batch_size=self.batch_size, **extra))

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._ensure().query_embed([text]))).tolist()


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """The process-wide embedder. There is one, and it is not selectable."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
