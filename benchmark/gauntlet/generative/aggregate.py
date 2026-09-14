"""Aggregate Track G results: completeness with CIs, the long-horizon decay curve, Synapse delta."""

from __future__ import annotations

from ..models import HarnessMeta
from ..scoring.stats import bootstrap_ci, mean, pass_hat_k, std
from .models import AppBrief, GenerativeResult

_BINS = 10  # horizon buckets (normalized feature position 0..1)
_REL_K = 5  # report pass^1..pass^k reliability up to this many seeds


def _reliability(rows: list[GenerativeResult]) -> dict:
    """τ-bench-style pass^k over seeds: a seed 'succeeds' iff the build is fully complete that seed.
    Computed per brief (n_seeds, full-complete seeds) then averaged, so it is not conflated across briefs."""

    if not rows:
        return {"k": [], "pass_hat_k": [], "full_complete_rate": 0.0}
    kmax = min(_REL_K, min(r.n_seeds for r in rows))
    ks = list(range(1, kmax + 1))
    per_row = [(r.n_seeds, sum(1 for c in r.seed_completeness if c >= 0.999)) for r in rows]
    curve = [round(mean([pass_hat_k(n, c, k) for n, c in per_row]), 4) for k in ks]
    return {"k": ks, "pass_hat_k": curve,
            "full_complete_rate": round(mean([c / n for n, c in per_row]), 4)}


def _composite(m: dict) -> float:
    # gate on build, then weight completeness + held-out robustness + visual + plan + honesty +
    # security + code health (the repo/project lesson: grade ALL quality axes, not just completeness)
    return round(
        m["build_rate"] * (
            0.40 * m["completeness"] + 0.15 * m["robustness"] + 0.12 * m["visual"]
            + 0.10 * m["plan"] + 0.08 * m["honesty"] + 0.10 * m["security"]
            + 0.05 * m["code_quality"]),
        4,
    )


def _gen_checks(rows: list[GenerativeResult]) -> dict:
    from ..checks import checks_block

    # functionality: shown e2e passes; robustness: held-out variants; quality: ruff+mypy; security: clean scan
    func = (sum(sum(r.feature_pass_counts) for r in rows),
            sum(r.feature_count * r.n_seeds for r in rows))
    held = (sum(r.held_out_passed for r in rows), sum(r.held_out_total for r in rows))
    qual = (sum(2.0 * r.code_quality for r in rows), 2.0 * len(rows))
    sec = (sum(1.0 for r in rows if r.findings == 0), float(len(rows)))  # apps with a clean scan
    block: dict[str, tuple[float, float]] = {"functionality": func}
    if held[1]:
        block["robustness"] = held
    block["quality"] = qual
    block["security"] = sec
    return checks_block(block)


def aggregate_generative(
    briefs: list[AppBrief], results: list[GenerativeResult], harnesses: list[HarnessMeta]
) -> dict:
    by_h = {h.id: [r for r in results if r.harness_id == h.id] for h in harnesses}
    uses_synapse = {h.id: h.uses_synapse for h in harnesses}
    per_harness: dict[str, dict] = {}

    for hid, rows in by_h.items():
        if not rows:
            per_harness[hid] = {
                "build_rate": None, "completeness": None, "completeness_ci": [None, None],
                "completeness_std": None, "plan": None, "visual": None, "honesty": None,
                "robustness": None, "security": None, "code_quality": None, "guardrail": None,
                "horizon_curve": [None] * _BINS, "reliability": _reliability([]),
                "checks": _gen_checks([]), "synapse_backend": "unavailable",
                "uses_synapse": uses_synapse[hid], "degraded": ["infrastructure"],
                "evaluable": False, "g_score": None,
            }
            continue
        seed_completeness = [c for r in rows for c in r.seed_completeness]
        guardrails = [r.guardrail_score for r in rows if r.guardrail_score is not None]
        degraded = sorted({signal for row in rows for signal in row.degraded})
        per_harness[hid] = {
            "build_rate": round(mean([r.build_pass / r.n_seeds for r in rows]), 4),
            "completeness": round(mean([sum(r.seed_completeness) / r.n_seeds for r in rows]), 4),
            "completeness_ci": list(bootstrap_ci([mean(r.seed_completeness) for r in rows])),
            "completeness_std": round(std(seed_completeness), 4),
            "plan": None if "trajectory" in degraded else round(mean([r.plan_score for r in rows]), 4),
            "visual": None if "visual" in degraded else round(mean([r.visual_score for r in rows]), 4),
            "honesty": None if "honesty" in degraded else round(mean([r.honesty for r in rows]), 4),
            "robustness": round(mean([r.robustness for r in rows]), 4),
            "security": round(mean([r.security for r in rows]), 4),
            "code_quality": round(mean([r.code_quality for r in rows]), 4),
            "guardrail": round(mean(guardrails), 4) if guardrails else None,
            "horizon_curve": _horizon_curve(rows),
            "reliability": _reliability(rows),
            "checks": _gen_checks(rows),  # test-counted success: features + lint/type, categorized
            "synapse_backend": rows[0].synapse_backend if rows else "shim",
            "uses_synapse": uses_synapse[hid],
            "degraded": degraded,
            "evaluable": bool(rows) and not degraded,
        }
        per_harness[hid]["g_score"] = (
            _composite(per_harness[hid]) if per_harness[hid]["evaluable"] else None
        )

    return {
        "per_harness": per_harness,
        "feature_count": sum(len(b.features) for b in briefs),
        "synapse_delta": _delta(per_harness, harnesses),
    }


def _horizon_curve(rows: list[GenerativeResult]) -> list[float]:
    """Mean feature pass-rate by normalized feature position, across briefs (the decay curve)."""

    buckets: list[list[float]] = [[] for _ in range(_BINS)]
    for r in rows:
        for i, rate in enumerate(r.feature_rate):  # smooth fixed-sample estimate
            pos = i / (r.feature_count - 1) if r.feature_count > 1 else 0.0
            buckets[min(_BINS - 1, int(pos * _BINS))].append(rate)
    return [round(mean(b), 4) if b else None for b in buckets]


def _delta(per_harness: dict, harnesses: list[HarnessMeta]) -> dict:
    raw = next((h.id for h in harnesses if h.role == "raw"), None)
    syn = next((h.id for h in harnesses if h.uses_synapse), None)
    if raw is None or syn is None:
        return {}
    r, s = per_harness[raw], per_harness[syn]

    def adv(metric: str) -> dict:
        raw_value, synapse_value = r[metric], s[metric]
        delta = (
            round(synapse_value - raw_value, 4)
            if raw_value is not None and synapse_value is not None
            else None
        )
        return {"raw": raw_value, "synapse": synapse_value, "delta": delta}

    return {"raw": raw, "synapse": syn, "completeness": adv("completeness"),
            "plan": adv("plan"), "honesty": adv("honesty"), "robustness": adv("robustness"),
            "security": adv("security"), "g_score": adv("g_score")}
