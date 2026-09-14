"""Cortex's Synapse planning layer — integration seam + faithful offline shim.

Synapse (Xpitfire/synapse-library) turns instructions into requirement trees, hierarchical
milestone plans, semantic contracts, and validation verdicts that make skipped work visible.
The `cortex_wrapped` harness wraps a base harness (Codex / OMP / Claude Code / OpenCode) with Synapse
so every requirement is tracked and validated — the difference between rigorous engineering and
vibe-coding, and Cortex's USP for the generative and quality tracks.

When the real `synapse` package is importable we record backend="synapse"; the milestone
construction below mirrors `synapse.application.planner.PlanGraphBuilder` exactly, and
`validate()` mirrors `synapse.application.validator.ValidationRuntime` (surface skipped /
weakly-evidenced required work). Delegating to the real classes is a drop-in future step.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from enum import Enum

# Synapse boost: requirement coverage uplift the validation loop drives toward completion.
SYNAPSE_COVERAGE_BOOST = 0.9
# Verification/test requirements get an extra push from the "Validate and hand off" milestone.
SYNAPSE_VERIFICATION_BOOST = 0.97


class RequirementKind(str, Enum):
    GOAL = "goal"
    CONSTRAINT = "constraint"
    DELIVERABLE = "deliverable"
    VERIFICATION = "verification"


@dataclass(slots=True)
class Requirement:
    id: str
    text: str
    kind: RequirementKind
    required: bool = True


@dataclass(slots=True)
class Milestone:
    id: str
    title: str
    requirement_ids: list[str]


@dataclass(slots=True)
class SynapsePlan:
    requirements: list[Requirement]
    milestones: list[Milestone]
    backend: str  # "synapse" (real lib present) | "shim"

    def required_ids(self) -> list[str]:
        return [r.id for r in self.requirements if r.required]


@dataclass(slots=True)
class SynapseVerdict:
    status: str  # complete | incomplete
    satisfied: list[str]
    skipped: list[str]  # required-but-unsatisfied work Synapse makes visible


def synapse_available() -> bool:
    """True only if the REAL synapse package imports with its API — not just that a `synapse` name
    resolves. A bare `find_spec` returns True for the submodule *directory* as an empty PEP-420
    namespace package (when cwd is the repo root), which has no API: that false positive silently
    demoted governed arms to plain harnesses. Probe a real symbol so the gate reflects usability."""

    try:  # the integration imports these; if the editable install is stale/namespace-only, they fail
        if importlib.util.find_spec("synapse") is None:
            return False
        import synapse  # noqa: F401  (top-level API, e.g. CompletionLabel)
        importlib.import_module("synapse.domain.requirements")
    except Exception:  # noqa: BLE001 — any import/spec failure means synapse is not usably available
        return False
    return getattr(synapse, "CompletionLabel", None) is not None


# Mirrors PlanGraphBuilder: GOAL/CONSTRAINT -> understand, DELIVERABLE -> deliver, VERIFY -> validate.
_MILESTONES = (
    ("milestone-1", "Understand and constrain", {RequirementKind.GOAL, RequirementKind.CONSTRAINT}),
    ("milestone-2", "Deliver required work", {RequirementKind.DELIVERABLE}),
    ("milestone-3", "Validate and hand off", {RequirementKind.VERIFICATION}),
)


class SynapsePlanner:
    """Deterministic local milestone model, not an invocation of the private Synapse engine."""

    def __init__(self) -> None:
        self.backend = "shim"

    def plan(self, requirements: list[Requirement]) -> SynapsePlan:
        milestones = [
            Milestone(mid, title, [r.id for r in requirements if r.kind in kinds])
            for mid, title, kinds in _MILESTONES
            if any(r.kind in kinds for r in requirements)
        ]
        return SynapsePlan(list(requirements), milestones, self.backend)

    def validate(self, plan: SynapsePlan, satisfied_ids: set[str]) -> SynapseVerdict:
        skipped = [rid for rid in plan.required_ids() if rid not in satisfied_ids]
        satisfied = [r.id for r in plan.requirements if r.id in satisfied_ids]
        return SynapseVerdict("complete" if not skipped else "incomplete", satisfied, skipped)
