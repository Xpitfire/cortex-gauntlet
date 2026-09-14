"""Reproducibility statistics: Wilson interval, pass@k estimator, bootstrap CI (stdlib only)."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """95% Wilson score interval for a binomial proportion."""

    if not 0 <= successes <= n or not math.isfinite(z) or z <= 0:
        raise ValueError("Wilson requires 0 <= successes <= n and finite z > 0")
    if n == 0:
        return (None, None)
    phat = successes / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator of P(at least one of k draws is a 'success') given c/n successes.

    For Track S a 'success' is an attack that complied, so this is attack-success@k — the
    adversary's odds with k attempts. 1 - C(n-c, k)/C(n, k).
    """

    if not all(type(v) is int for v in (n, c, k)) or not (0 <= c <= n and 1 <= k <= n):
        raise ValueError("pass@k requires integers 0 <= c <= n and 1 <= k <= n")
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Reliability: unbiased estimate that ALL k i.i.d. trials succeed, given c/n succeeded.

    The τ-bench pass^k consistency measure (non-increasing in k): the probability that a random
    size-k subset of the n trials is all successes, C(c,k)/C(n,k). pass^1 is the plain success rate;
    higher k rewards a harness that succeeds *reliably*, not merely once.
    """

    if not all(type(v) is int for v in (n, c, k)) or not (0 <= c <= n and 1 <= k <= n):
        raise ValueError("pass^k requires integers 0 <= c <= n and 1 <= k <= n")
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


def bootstrap_ci(
    values: Sequence[float], iters: int = 1000, alpha: float = 0.05, seed: int = 0,
    *, weights: Sequence[int] | None = None,
) -> tuple[float | None, float | None]:
    """Resample case clusters, recomputing the (optionally attempt-weighted) mean."""

    if not 0 < alpha < 1 or iters < 1:
        raise ValueError("bootstrap requires 0 < alpha < 1 and iters >= 1")
    n = len(values)
    if n == 0:
        return (None, None)
    if weights is not None and (len(weights) != n or any(w <= 0 for w in weights)):
        raise ValueError("bootstrap weights must be positive and match the case count")
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample = [rng.randrange(n) for _ in range(n)]
        if weights is None:
            means.append(mean([values[i] for i in sample]))
        else:
            means.append(sum(values[i] * weights[i] for i in sample) / sum(weights[i] for i in sample))
    means.sort()
    lo = means[int((alpha / 2) * iters)]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (round(lo, 4), round(hi, 4))
