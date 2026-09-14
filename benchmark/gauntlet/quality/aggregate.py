"""Aggregate Track Q results into per-harness quality metrics + the Synapse delta."""

from __future__ import annotations

from collections import Counter

from ..checks import CHECK_CATEGORIES, checks_block
from ..models import HarnessMeta
from .judge import DIMENSIONS
from .metrics import check_breakdown, smell_count
from .models import QualityResult, QualityTask

_GRADES = ((0.3, "A"), (0.7, "B"), (1.2, "C"), (1.8, "D"))


def _grade(debt: float) -> str:
    for threshold, grade in _GRADES:
        if debt < threshold:
            return grade
    return "E"


def aggregate_quality(
    tasks: list[QualityTask], results: list[QualityResult], harnesses: list[HarnessMeta]
) -> dict:
    by_h = {h.id: [r for r in results if r.harness_id == h.id] for h in harnesses}
    uses_synapse = {h.id: h.uses_synapse for h in harnesses}
    per_harness: dict[str, dict] = {}
    all_cwes: set[str] = set()

    for hid, rows in by_h.items():
        n = len(rows) or 1
        loc = sum(r.loc for r in rows) or 1
        vulns = sum(len(r.findings) for r in rows)
        smells = sum(smell_count(r.metrics) for r in rows)
        coverage = sum(r.requirement_coverage for r in rows) / n
        by_cwe = Counter(f.cwe for r in rows for f in r.findings)
        all_cwes |= set(by_cwe)
        complexity = sum(r.metrics.complexity / max(r.metrics.functions, 1) for r in rows) / n
        judge = {d: round(sum(r.judge.get(d, 0.0) for r in rows) / n, 3) for d in DIMENSIONS}
        functional_rows = [r for r in rows if r.dynamic_ran]
        functional = (
            sum(r.functional_rate for r in functional_rows) / len(functional_rows)
            if functional_rows else None
        )
        # categorized, test-COUNTED success: sum each check across cells (not one pass/fail per cell)
        # so a 6/7-functional cell with clean lint/types reads as ~90%, not a total failure, and the
        # rate is attributable to functionality vs quality (ruff+mypy) vs security
        cats = {cat: [0.0, 0.0] for cat in CHECK_CATEGORIES}
        for r in rows:
            for cat, cnt in check_breakdown(r).items():
                cats[cat][0] += cnt["passed"]
                cats[cat][1] += cnt["total"]
        checks = checks_block({cat: (p, t) for cat, (p, t) in cats.items()})
        debt = (vulns / n) * 0.4 + (smells / n) * 0.2 + (1 - coverage) * 1.0
        per_harness[hid] = {
            "vulns_total": vulns,
            "vulns_per_kloc": round(vulns / (loc / 1000), 2),
            "vulns_per_task": round(vulns / n, 3),
            "smells_per_task": round(smells / n, 3),
            "by_cwe": dict(by_cwe),
            "bad_deps": sum(len(r.bad_dependencies) for r in rows),
            "requirement_coverage": round(coverage, 4),
            "functional_rate": round(functional, 4) if functional is not None else None,
            "checks": checks,  # categorized, test-counted success (functionality/quality/security/overall)
            "complexity": round(complexity, 2),
            "duplication": round(sum(r.metrics.duplication_pct for r in rows) / n, 4),
            "judge": judge,
            "maintainability": {"grade": _grade(debt), "debt": round(debt, 3)},
            "loc": loc,
            "synapse_backend": rows[0].synapse_backend if rows else "shim",
            "uses_synapse": uses_synapse[hid],
        }

    by_cwe_chart = {
        cwe: {hid: per_harness[hid]["by_cwe"].get(cwe, 0) for hid in by_h}
        for cwe in sorted(all_cwes)
    }
    return {
        "per_harness": per_harness,
        "by_cwe": by_cwe_chart,
        "synapse_delta": _delta(per_harness, harnesses),
    }


def _delta(per_harness: dict, harnesses: list[HarnessMeta]) -> dict:
    """Synapse advantage vs the raw harness; delta>0 = Synapse better on every metric."""

    raw = next((h.id for h in harnesses if h.role == "raw"), None)
    syn = next((h.id for h in harnesses if h.uses_synapse), None)
    if raw is None or syn is None:
        return {}
    r, s = per_harness[raw], per_harness[syn]

    def adv(metric: str, raw_v: float, syn_v: float) -> dict:
        return {"raw": raw_v, "synapse": syn_v, "delta": round(syn_v - raw_v, 4)}

    return {
        "raw": raw,
        "synapse": syn,
        # coverage + functional: higher synapse is the advantage
        "requirement_coverage": adv("cov", r["requirement_coverage"], s["requirement_coverage"]),
        "functional_rate": adv("fn", r.get("functional_rate") or 0.0, s.get("functional_rate") or 0.0),
        # vulns/debt: lower synapse is the advantage, so flip the sign so delta>0 = better
        "vulns_per_task": {"raw": r["vulns_per_task"], "synapse": s["vulns_per_task"],
                           "delta": round(r["vulns_per_task"] - s["vulns_per_task"], 4)},
        "debt": {"raw": r["maintainability"]["debt"], "synapse": s["maintainability"]["debt"],
                 "delta": round(r["maintainability"]["debt"] - s["maintainability"]["debt"], 4)},
    }
