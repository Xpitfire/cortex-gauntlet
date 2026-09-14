"""Track P data model: the open brief, the built candidate (sandbox output), and the scored result."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProjectBrief:
    """The open-ended build prompt + the hidden acceptance spec + reference assets."""

    id: str
    title: str
    prompt: str  # BRIEF.md — what the harness receives
    acceptance: dict  # hidden: journeys, rest, pwa, a11y, robustness, visual anchors, descriptors
    screenshots: list[str]  # reference frame paths (relative to the fixture)
    catalog: dict  # seed data handed to the harness

    @property
    def capability_descriptors(self) -> list[str]:
        return list(self.acceptance.get("capability_descriptors", []))

    @property
    def architecture_anchors(self) -> list[str]:
        return list(self.acceptance.get("architecture_anchors", []))


@dataclass(slots=True)
class Candidate:
    """What a harness produced, as observed in the sandbox (or modelled in mock mode).

    `capabilities` is the BEHAVIOUR-derived capability trajectory (descriptors of journeys that
    actually passed / routes served) — the VERTEX candidate. `screenshots` are real in-sandbox
    renders keyed by screen. A mock candidate fills the same fields from a modelled outcome.
    """

    harness_id: str
    built: bool
    served: bool
    capabilities: list[str] = field(default_factory=list)
    journey_pass: dict[str, bool] = field(default_factory=dict)  # journey id -> passed
    journey_eval: dict[str, bool] = field(default_factory=dict)  # journey id -> evaluable in the sandbox
    #   (a stateful flow the offline probe could not drive is excluded from functional, not counted failed)
    pwa_a11y: dict[str, bool] = field(default_factory=dict)
    robustness: dict[str, bool] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)  # repo tree (path -> content)
    module_descriptors: list[str] = field(default_factory=list)  # for the architecture VERTEX view
    screenshots: dict[str, str] = field(default_factory=dict)  # screen -> artifact path
    error: str | None = None  # sandbox-level failure (a crash is data, never aborts the suite)


@dataclass(slots=True)
class SignalVector:
    """The per-candidate multi-signal score (every component persisted; composite is gated)."""

    build: int  # {0,1} hard gate
    functional: float  # passed journeys, weighted
    pwa_a11y: float
    code_health: float
    robustness: float
    security: float  # Semgrep severity-weighted scan of the repo (1.0 = clean)
    vertex: float  # capability + architecture cross-similarity (baseline-normalized)
    visual: float  # vision-judge fidelity vs reference frames
    code_arch: float  # rubric-judge architecture/quality
    ux: float  # journey coherence
    composite: float  # gated weighted sum
    detail: dict = field(default_factory=dict)  # sub-scores, CIs, judge provenance, vertex parts


@dataclass(slots=True)
class ProjectResult:
    brief_id: str
    harness_id: str
    signals: SignalVector
    files: dict = field(default_factory=dict)  # captured repo for the code viewer
    screenshots: dict = field(default_factory=dict)
    sandbox_backend: str = "mock"  # "docker" | "static-only" | "mock"
    error: str | None = None
    # behaviour-derived trajectories persisted so VERTEX-QE (consensus + correlation) can be computed at
    # aggregate time across the arm pool, not just per-candidate during scoring
    capabilities: list = field(default_factory=list)
    module_descriptors: list = field(default_factory=list)
