"""Track Q data model: code-gen tasks, generated artifacts, findings, results."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..analysis.models import CodeMetrics, Finding  # re-exported: shared analysis data model
from ..enums import Language

__all__ = ["CodeMetrics", "Finding", "QualityResult", "QualityTask", "RequirementSpec"]


@dataclass(slots=True)
class RequirementSpec:
    """One requirement of a code task, with the safe vs vibe-coded snippet for each outcome."""

    id: str
    text: str
    kind: str  # RequirementKind value: goal | constraint | deliverable | verification
    category: str  # sql | secrets | crypto | command | deserialization | tests | error_handling
    good_code: str = ""  # single-file mock snippet; empty for multi-file tasks (live-only)
    bad_code: str = ""
    cwe: str | None = None  # CWE flagged by SAST when this requirement is NOT satisfied
    test: str = ""  # hidden ground-truth pytest that passes iff this requirement is satisfied
    required: bool = True
    evidence: str = ""  # spec-derived marker (symbol/def) present iff satisfied — drives the Synapse loop, NOT the hidden test


@dataclass(slots=True)
class QualityTask:
    id: str
    title: str
    language: Language
    instruction: str
    scaffold: str  # file header / imports the snippets slot into
    requirements: list[RequirementSpec]
    # multi-file tasks: reference package (path -> content); the mock uses it directly, live captures its own
    files: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class QualityResult:
    task_id: str
    harness_id: str
    language: str
    code: str
    loc: int
    findings: list[Finding]
    metrics: CodeMetrics
    requirement_coverage: float
    skipped_requirements: list[str]
    bad_dependencies: list[str]
    synapse_backend: str
    functional_passed: int  # hidden ground-truth tests that passed (real pytest)
    functional_total: int
    functional_rate: float
    dynamic_ran: bool
    test_output: str = ""
    files: dict = field(default_factory=dict)  # generated output files (path -> content) for the code viewer
    judge: dict = field(default_factory=dict)  # {architecture, readability, interface}
    gen_error: str = ""  # live: the harness failed to produce code (auth/provider/parse) — an ERROR, not a FAIL
    rate_limited: bool = False  # the failure was a provider rate limit — pause/resume, never count as failed
