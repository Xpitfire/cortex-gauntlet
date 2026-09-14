"""Mock code generator: assemble code from per-requirement snippets by coverage.

Real harnesses would generate code via the CLI (a CodeGenAdapter — deferred). Here requirement
coverage is a deterministic function of the harness `code_quality` and whether it is
Synapse-wrapped: Synapse's plan + validation loop drives required (and especially verification)
work to completion, so the cortex_wrapped harness covers more requirements → safer, cleaner code.
"""

from __future__ import annotations

import hashlib

from ..models import HarnessMeta
from ..synapse import (
    SYNAPSE_COVERAGE_BOOST,
    SYNAPSE_VERIFICATION_BOOST,
    Requirement,
    RequirementKind,
    SynapsePlanner,
)
from .models import QualityTask


def _frac(key: str) -> float:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def _satisfy_prob(harness: HarnessMeta, kind: RequirementKind) -> float:
    base = harness.code_quality
    if not harness.uses_synapse:
        return base
    boost = SYNAPSE_VERIFICATION_BOOST if kind is RequirementKind.VERIFICATION else SYNAPSE_COVERAGE_BOOST
    return base + (1 - base) * boost


def generate(
    task: QualityTask, harness: HarnessMeta, planner: SynapsePlanner
) -> tuple[str, float, list[str], str, set[str]]:
    requirements = [Requirement(r.id, r.text, RequirementKind(r.kind)) for r in task.requirements]
    plan = planner.plan(requirements)
    satisfied: set[str] = set()
    snippets: list[str] = []
    for spec in task.requirements:
        ok = _frac(f"{task.id}:{spec.id}:{harness.id}") < _satisfy_prob(harness, RequirementKind(spec.kind))
        if ok:
            satisfied.add(spec.id)
        snippets.append(spec.good_code if ok else spec.bad_code)
    code = task.scaffold + "\n" + "\n".join(snippets) + "\n"
    verdict = planner.validate(plan, satisfied)
    coverage = len(satisfied) / len(requirements) if requirements else 0.0
    return code, coverage, verdict.skipped, plan.backend, satisfied
