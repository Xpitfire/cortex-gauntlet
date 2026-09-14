"""Track G data model: app briefs, features, and per-(brief, harness) generative results."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..enums import Language


@dataclass(slots=True)
class FeatureSpec:
    id: str
    name: str
    category: str  # ui | api | data | auth | payment | realtime | admin | export
    e2e: str  # the end-to-end check a real Playwright/REST/DB-state scorer would run


@dataclass(slots=True)
class AppBrief:
    id: str
    title: str
    language: Language
    stack: str
    instruction: str
    features: list[FeatureSpec]
    architecture: str = ""  # data model / stack detail for the spec
    acceptance: str = ""  # what "done" means
    mandated_stack: str | None = None  # guardrail variant: a required framework/architecture


@dataclass(slots=True)
class FeatureOutcome:
    feature_id: str
    name: str
    passed: bool  # built and passed its e2e check
    claimed: bool  # the harness reported it as done


@dataclass(slots=True)
class GenerativeResult:
    brief_id: str
    harness_id: str
    language: str
    n_seeds: int
    feature_count: int
    build_pass: int  # seeds where the app built/booted
    feature_pass_counts: list[int]  # per feature: seeds passing e2e (len = feature_count)
    feature_claim_counts: list[int]
    seed_completeness: list[float]  # per seed: passed features / total (for CI + mean±std)
    feature_rate: list[float]  # per-feature pass rate at a high fixed sample (smooth decay curve)
    plan_score: float  # long-horizon plan/trajectory quality
    visual_score: float
    honesty: float  # 1 - over-claim rate (claimed-but-failed features)
    guardrail_score: float | None  # adherence to a mandated stack (None if not mandated)
    milestones: list[str]  # representative plan (Synapse milestones vs ad-hoc)
    rep_features: list[FeatureOutcome] = field(default_factory=list)
    screenshot: str | None = None  # rendered app mock, relative to the run dir
    synapse_backend: str = "shim"
    files: dict = field(default_factory=dict)  # generated app files (path -> content) for the code viewer
    # additive static-quality of the generated app (ruff lint + mypy types); 1.0 = clean, a no-op when
    # the build is non-Python or produced no files (analysis.lint_types — secondary to the e2e signal)
    lint_issues: int = 0
    type_errors: int = 0
    code_quality: float = 1.0
    # security of the generated app: a Semgrep/Bandit scan of the captured files (1.0 = clean), the same
    # signal Track P uses — so a "complete" app that ships vulnerable code is graded down.
    security: float = 1.0
    findings: int = 0
    security_tool: str = ""
    # held-out robustness: pass rate over probe variants the arm never saw (different inputs / a 2nd
    # turn) — the anti-overfit axis; a hardcoded answer to the fixed probe fails these.
    robustness: float = 1.0
    held_out_passed: int = 0
    held_out_total: int = 0
    degraded: list[str] = field(default_factory=list)
