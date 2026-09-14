"""VERTEX — Vector Embedding for Relational Trajectory Evaluation through Cross-similarity.

Scores a candidate behavior trajectory against a benchmark item's reference descriptor set:
embed both sides, form the candidate x reference cross-similarity matrix, and read the score off it.
The reference is a descriptor sequence, not an estimated probability distribution.
Sensitive to incremental quality independent of task completion. Two views:
  - unordered: a BERTScore-style bidirectional best-match F (which capabilities are present, how well);
  - ordered: DTW alignment with a linear positional distance-decay.

Reference reading on trajectory scoring by embedding cross-similarity: arXiv:2402.00854 and
arXiv:2405.20309.
Both are affinely recalibrated against the mean-similarity baseline of the candidate×reference matrix
(η_b(b)=0, η_b(1)=1). This is not a zero-at-chance guarantee: unrelated-input scores depend
on descriptor lengths, ordering, and embedding geometry — see §5.1 of the paper.

Embeddings come from the shared `embedding` module (sentence-transformers `all-MiniLM-L6-v2` by
default, or `GAUNTLET_VERTEX_MODEL=none` for the deterministic hashing embedding that keeps the scorer
offline + tests reproducible). A *named* model that fails to load raises rather than silently swapping
in the hashing embedding. Pure-Python: trajectories are short (tens of descriptors), no numpy needed.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from .embedding import cosine as _cos
from .embedding import embed_texts

DEFAULT_MODEL = "all-MiniLM-L6-v2"  # efficient local default: 384-dim, ~90MB, fast on CPU


def resolve_model() -> str | None:
    """Embedding model id from $GAUNTLET_VERTEX_MODEL (default all-MiniLM-L6-v2; 'none'/'' → hashing)."""

    env = os.environ.get("GAUNTLET_VERTEX_MODEL")
    if env is None:
        return DEFAULT_MODEL
    return None if env.strip().lower() in ("", "none", "off", "fallback") else env.strip()


@dataclass(slots=True)
class VertexScore:
    vertex: float  # combined, baseline-normalized [0,1]
    f_unordered: float  # bidirectional best-match F (normalized)
    ordered: float  # DTW-with-decay similarity (normalized)
    precision: float
    recall: float
    backend: str  # "sentence-transformers:<model>" | "hash-fallback" | "empty" (degenerate inputs)


def _cross_sim(cand: list[list[float]], ref: list[list[float]]) -> list[list[float]]:
    return [[_cos(c, r) for r in ref] for c in cand]


def _unordered_f(sim: list[list[float]]) -> tuple[float, float, float]:
    if not sim or not sim[0]:
        return 0.0, 0.0, 0.0
    # best matches are floored at 0 so P, Q ≥ 0 even for globally anti-aligned pairs — this keeps the
    # F formula's P+Q guard sound and matches the docs' stated bounds (and project/judge.py's kernel)
    precision = sum(max(0.0, max(row)) for row in sim) / len(sim)  # each candidate → its best reference
    recall = sum(max(0.0, max(col)) for col in zip(*sim, strict=False)) / len(sim[0])  # each ref covered
    f = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f


def _dtw_decay(sim: list[list[float]], lam: float) -> float:
    """DTW alignment minimizing cosine-distance × linear positional decay; → similarity in [0,1]."""

    m, n = len(sim), len(sim[0])
    inf = float("inf")
    cost = [[inf] * (n + 1) for _ in range(m + 1)]
    cost[0][0] = 0.0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # cosine distance, penalized when the aligned steps sit far apart in their trajectories
            d = (1.0 - sim[i - 1][j - 1]) * (1.0 + lam * abs((i - 1) / m - (j - 1) / n))
            cost[i][j] = d + min(cost[i - 1][j], cost[i][j - 1], cost[i - 1][j - 1])
    path_len = m + n  # upper bound on the monotonic path length (cheap, stable normalizer)
    return max(0.0, 1.0 - cost[m][n] / path_len)


def _normalize(value: float, baseline: float) -> float:
    return max(0.0, min(1.0, (value - baseline) / (1.0 - baseline))) if baseline < 1.0 else 0.0


def vertex_score(
    candidate: list[str], reference: list[str], *, alpha: float = 0.6, lam: float = 0.5,
    model: str | None = "__default__",
) -> VertexScore:
    """Cross-similarity of a candidate descriptor trajectory vs a reference distribution.

    `candidate`/`reference` are short natural-language descriptors (behaviour-derived, not claims).
    Returns the combined VERTEX score plus its components; deterministic under the hashing fallback.
    """

    if not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("alpha must be finite and in [0, 1]")
    if not math.isfinite(lam) or lam < 0:
        raise ValueError("lam must be finite and nonnegative")
    if not candidate or not reference:
        return VertexScore(0.0, 0.0, 0.0, 0.0, 0.0, "empty")
    if model == "__default__":
        model = resolve_model()
    vectors, backend = embed_texts(candidate + reference, model)
    cand, ref = vectors[: len(candidate)], vectors[len(candidate):]
    sim = _cross_sim(cand, ref)
    baseline = max(0.0, min(0.99, sum(sum(row) for row in sim) / (len(cand) * len(ref))))  # chance match
    precision, recall, f = _unordered_f(sim)
    ordered = _dtw_decay(sim, lam)
    f_norm, ordered_norm = _normalize(f, baseline), _normalize(ordered, baseline)
    vertex = alpha * f_norm + (1.0 - alpha) * ordered_norm
    return VertexScore(round(vertex, 4), round(f_norm, 4), round(ordered_norm, 4),
                       round(precision, 4), round(recall, 4), backend)
