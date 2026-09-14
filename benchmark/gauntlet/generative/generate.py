"""Mock generative harness with long-horizon decay — Synapse keeps the horizon flat.

The realistic effect this models: raw harnesses degrade as a build gets longer (they lose track
and silently drop later features), while a Synapse-wrapped harness tracks every feature as a
requirement and validates it, so completeness stays high across the whole horizon. Real harness
code-gen + Playwright/REST/DB-state e2e are documented seams.
"""

from __future__ import annotations

import hashlib

from ..models import HarnessMeta
from ..synapse import Requirement, RequirementKind, SynapsePlanner
from .judge import GenerativeJudge
from .models import AppBrief, FeatureOutcome, GenerativeResult

HORIZON_DECAY = 0.97  # raw harness: each later feature is a bit harder to keep complete
SYNAPSE_FEATURE_BOOST = 0.9
RAW_OVERCLAIM = 0.30  # share of failed features a raw harness still reports as "done"
HCURVE_SAMPLES = 64  # fixed sample for a smooth per-feature decay-curve estimate


def _frac(key: str) -> float:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def _build_prob(h: HarnessMeta) -> float:
    return 0.99 if h.uses_synapse else 0.7 + 0.3 * h.code_quality


def _feature_prob(h: HarnessMeta, index: int) -> float:
    base = h.code_quality
    if h.uses_synapse:
        return base + (1 - base) * SYNAPSE_FEATURE_BOOST
    return base * (HORIZON_DECAY**index)  # decays with feature position (the long horizon)


def _plan_requirements(brief: AppBrief) -> list[Requirement]:
    reqs = [Requirement(f.id, f.name, RequirementKind.DELIVERABLE) for f in brief.features]
    reqs.append(Requirement("verify", "validate all features end-to-end", RequirementKind.VERIFICATION))
    if brief.mandated_stack:
        reqs.insert(0, Requirement("stack", brief.mandated_stack, RequirementKind.CONSTRAINT))
    return reqs


def run_brief(
    brief: AppBrief, harness: HarnessMeta, planner: SynapsePlanner, judge: GenerativeJudge, seeds: int
) -> GenerativeResult:
    features = brief.features
    n = len(features)
    plan = planner.plan(_plan_requirements(brief))

    build_pass = 0
    pass_counts = [0] * n
    claim_counts = [0] * n
    seed_completeness: list[float] = []
    rep_features: list[FeatureOutcome] = []

    for s in range(seeds):
        built = _frac(f"{brief.id}:build:{harness.id}:{s}") < _build_prob(harness)
        build_pass += built
        seed_passed = 0
        for i, feature in enumerate(features):
            ok = built and _frac(f"{brief.id}:{feature.id}:{harness.id}:{s}") < _feature_prob(harness, i)
            overclaim = (
                not harness.uses_synapse
                and _frac(f"{brief.id}:{feature.id}:claim:{harness.id}:{s}") < RAW_OVERCLAIM
            )
            claimed = ok or overclaim
            pass_counts[i] += ok
            claim_counts[i] += claimed
            seed_passed += ok
            if s == 0:
                rep_features.append(FeatureOutcome(feature.id, feature.name, ok, claimed))
        seed_completeness.append(round(seed_passed / n, 4))

    # smooth per-feature pass-rate estimate (same model, many samples) for the decay curve
    feature_rate = [
        round(
            sum(
                1
                for s in range(HCURVE_SAMPLES)
                if _frac(f"{brief.id}:build:{harness.id}:hc{s}") < _build_prob(harness)
                and _frac(f"{brief.id}:{feature.id}:{harness.id}:hc{s}") < _feature_prob(harness, i)
            )
            / HCURVE_SAMPLES,
            4,
        )
        for i, feature in enumerate(features)
    ]

    completeness = sum(seed_completeness) / seeds
    total_claimed, total_passed = sum(claim_counts), sum(pass_counts)
    visual = round(min(1.0, 0.3 + 0.6 * completeness + (0.1 if harness.uses_synapse else 0.0)), 3)
    guardrail = None
    if brief.mandated_stack:
        guardrail = round(0.95 if harness.uses_synapse else 0.45 + 0.3 * harness.code_quality, 3)
    # modeled security + held-out robustness (no real scan/probe in mock): a governed arm ships cleaner
    # code and overfits less, so raw arms score a little lower on both — the LIVE path measures them.
    security = round(min(1.0, 0.8 + 0.15 * harness.code_quality + (0.05 if harness.uses_synapse else 0.0)), 3)
    robustness = round(min(1.0, completeness * (1.0 if harness.uses_synapse else 0.8)), 3)

    return GenerativeResult(
        brief_id=brief.id, harness_id=harness.id, language=brief.language.value, n_seeds=seeds,
        feature_count=n, build_pass=build_pass, feature_pass_counts=pass_counts,
        feature_claim_counts=claim_counts, seed_completeness=seed_completeness,
        feature_rate=feature_rate,
        plan_score=judge.plan_score(brief, plan.milestones, completeness, harness.uses_synapse),
        visual_score=visual,
        honesty=round(total_passed / total_claimed, 3) if total_claimed else 1.0,
        guardrail_score=guardrail,
        milestones=[f"{m.title} ({len(m.requirement_ids)})" for m in plan.milestones],
        rep_features=rep_features, synapse_backend=plan.backend,
        # mock mode has no real ruff/mypy pass, so model the static-quality signal off the harness's
        # modeled code_quality (Synapse lifts it) instead of leaving the field at its 1.0 default — that
        # default would make the generative cell's code_quality detail read a constant 100% in mock runs.
        code_quality=round(min(1.0, harness.code_quality + (0.1 if harness.uses_synapse else 0.0)), 3),
        security=security, security_tool="modeled", robustness=robustness,
    )
