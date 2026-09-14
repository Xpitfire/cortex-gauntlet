"""Categorized, test-COUNTED success blocks shared by the code tracks (quality / repo / generative).

The point: a cell that runs N checks should count EACH check toward the success rate and attribute it
to the right axis — functionality (tests), quality (ruff lint + mypy types), security (SAST) — instead
of collapsing to one all-or-nothing pass/fail. So 6/7 functional tests with clean lint/types reads as
~90%, not a total failure, and the rate is decomposable per category.
"""

from __future__ import annotations

CHECK_CATEGORIES = ("functionality", "quality", "security")


def checks_block(cats: dict[str, tuple[float, float]]) -> dict:
    """Per-category {passed, total, rate} + a micro-averaged `overall`, from summed (passed, total)
    pairs. Categories with a zero total are still emitted (rate=None) so the report can label them."""

    out: dict[str, dict] = {}
    for cat, (passed, total) in cats.items():
        out[cat] = {"passed": round(passed, 2), "total": round(total, 2),
                    "rate": round(passed / total, 4) if total else None}
    tp = sum(p for p, _ in cats.values())
    tt = sum(t for _, t in cats.values())
    out["overall"] = {"passed": round(tp, 2), "total": round(tt, 2),
                      "rate": round(tp / tt, 4) if tt else None}
    return out
