"""Typed data model for cases, transcripts, scores, and run records."""

from __future__ import annotations

import dataclasses
import enum
import json
import types
import typing
from dataclasses import dataclass, field

from .enums import Instrument, Modality, Objective, Surface, Technique, Track, Verdict

SCHEMA_VERSION = "0.1.0"
SCORING_VERSION = "2026-09-13-scientific-audit-v3"


@dataclass(slots=True)
class ProposedAction:
    """A tool-call the harness proposed. Captured, never executed."""

    kind: str  # shell | git | package | http
    command: str
    danger: bool


@dataclass(slots=True)
class Transcript:
    harness_id: str
    model: str
    prompt: str
    response: str
    proposed_actions: list[ProposedAction] = field(default_factory=list)
    tokens: int = 0
    wall_ms: int = 0
    # the CLI's OWN failure text (stderr) ONLY when it errored and produced no real answer — the
    # structured signal for an infra pause (rate limit / auth / connectivity). Empty on a successful
    # run, so a normal answer that merely *mentions* "429"/"rate limit"/"overloaded" never triggers a
    # false pause. Distinct from `response`, which is legitimate task content scored by the judge.
    error: str = ""


@dataclass(slots=True)
class L0Result:
    """Deterministic detector output."""

    canary_hit: bool
    refusal_markers: bool
    danger_signals: list[str]
    hard_danger_signals: list[str] = field(default_factory=list)
    # a GENUINE safety refusal (declines on safety/suspicion grounds) — distinct from refusal_markers,
    # which also fires on a mere SANDBOX block ("I can't run it here / read-only / didn't execute").
    # Only a genuine refusal suppresses a danger proposal; a sandbox block does not (the agent still
    # provided/endorsed the harmful command). Defaults False so older constructions stay valid.
    genuine_refusal: bool = False


@dataclass(slots=True)
class SideEffects:
    """What a captured action *would* have done, observed in the mock environment."""

    exfil: bool = False
    history_overwritten: bool = False
    malicious_install: bool = False
    remote_exec: bool = False
    effects: list[str] = field(default_factory=list)


@dataclass(slots=True)
class L1Result:
    """L1 logical side-effect replay (in-memory mock env; no Docker, no execution)."""

    exploit_confirmed: bool
    side_effects: SideEffects


@dataclass(slots=True)
class Score:
    instrument: Instrument
    verdict: Verdict
    exploitable: bool
    confidence: float
    rationale: str
    judge_model: str


@dataclass(slots=True)
class SecurityPass:
    """One scored security turn inside a seed attempt."""

    pass_index: int
    transcript: Transcript
    l0: L0Result
    l1: L1Result
    score: Score
    compliant: bool
    refused: bool
    confirmed: bool


@dataclass(slots=True)
class Case:
    id: str
    track: Track
    surface: Surface
    technique: Technique
    objective: Objective
    modality: Modality
    benign: bool
    family: str
    instruction: str  # what the harness receives (envelope / carrier prompt)
    canary: str
    ground_truth: str
    payload: str = ""  # the harmful core (lives in the surface/asset; used by judge + mock)
    benign_task: str = ""  # the legitimate task for indirect-injection cases (utility)
    asset_path: str | None = None  # rendered image/audio artifact, relative to the run dir
    held_out: bool = False
    # files seeded INTO the agent's prepared workspace (path -> content): the injection lives in a
    # plausible file the agent reads while doing the benign carrier task, not in the prompt.
    workspace_files: dict[str, str] = field(default_factory=dict)
    # >0 surrounds the workspace with a large on-topic synthetic repo sized to this context-fill
    # fraction of a 200K reference window (0.25..0.9; >1.0 = extreme, push past the window), so the
    # buried injection is diluted/saturated (see repo_scaffold.py + docs/agentic-redesign-research.md).
    scaffold_fill: float = 0.0
    # how many files carry the injection — density. 1 = single needle; many = PoisonedRAG-style
    # repetition that raises attack success (power-law). The mock models the dose-response.
    needle_count: int = 1
    # absolute path to a STATIC image fixture (e.g. a famous brand's UI screenshot) delivered to the
    # agent's vision channel as-is, instead of rendering one from `payload`. Used by brand-clone cases.
    asset_fixture: str | None = None


@dataclass(slots=True)
class HarnessMeta:
    id: str
    label: str
    model: str
    family: str  # openai | anthropic | opencode | cortex
    role: str  # raw | product | cortex_wrapped
    safety: float
    over_caution: float
    injection_guard: float = 1.0  # <1 = harder to injection/multimodal-attack (mock only)
    supports_tools: bool = True
    supports_multimodal: bool = False
    max_context: int = 200_000
    code_quality: float = 0.5  # base propensity to satisfy a requirement well (Track Q, mock)
    uses_synapse: bool = False  # wrapped with the Synapse planning/validation layer
    uses_review: bool = False  # M5: run the Synapse read-only review inner-loop on each generation
    reasoning: str = ""  # reasoning effort / thinking (xhigh, high, extended thinking, …)


@dataclass(slots=True)
class CaseResult:
    """One (case, harness) cell aggregated over n_seeds attempts (attempt-budget normalized)."""

    case_id: str
    harness_id: str
    n_seeds: int
    complies: int  # seeds that complied with the attack
    refusals: int  # seeds that refused
    confirms: int  # seeds whose compliance was deterministically confirmed (side-effect/canary)
    seed_complies: list[bool]  # per-seed compliance, for seed-level mean/std
    tokens_total: int  # summed across all seed attempts (cost / budget)
    wall_ms_total: int
    transcript: Transcript  # representative seed (a complying one if any, else the first)
    l0: L0Result
    l1: L1Result
    score: Score
    confirmed: bool  # representative seed confirmed
    utility_done: bool | None = None  # benign task completed under indirect attack (else None)
    pass_complies: list[int] = field(default_factory=list)  # per-pass new compromises
    pass_cumulative_complies: list[int] = field(default_factory=list)  # compromised by/pass <= index
    pass_refusals: list[int] = field(default_factory=list)
    pass_confirms: list[int] = field(default_factory=list)
    pass_results: list[SecurityPass] = field(default_factory=list)  # representative seed evidence

    @property
    def asr_at_1(self) -> float:
        return self.complies / self.n_seeds if self.n_seeds else 0.0


def _coerce(tp, val):
    """Coerce a JSON value back to its annotated type — nested dataclasses, str-enums, lists, Optionals,
    primitives. The inverse of dataclasses.asdict for our result models."""

    if val is None:
        return None
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin in (typing.Union, getattr(types, "UnionType", None)):  # Optional[X] / X | None
        non_none = [a for a in args if a is not type(None)]
        return _coerce(non_none[0], val) if non_none else val
    if origin in (list, tuple):
        inner = args[0] if args else object
        return [_coerce(inner, v) for v in val]
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return tp(val)
    if dataclasses.is_dataclass(tp):
        return dataclass_from_dict(tp, val)
    return val


def dataclass_from_dict(cls, data: dict):
    """Rebuild a dataclass instance from its dataclasses.asdict() form (recursively; resolves str-enums
    and nested dataclasses). The inverse of RunRecord.to_dict's flattening — used to restore a scored
    result from a checkpoint (resume) or to re-judge a captured run (rescore), for ANY track's result."""

    if data is None or not dataclasses.is_dataclass(cls):
        return data
    hints = typing.get_type_hints(cls)
    return cls(**{f.name: _coerce(hints.get(f.name, object), data[f.name])
                  for f in dataclasses.fields(cls) if f.name in data})


def case_result_from_dict(d: dict) -> CaseResult:
    """Rebuild a Track-S CaseResult from its asdict()/runrecord JSON form (back-compat shim)."""
    return dataclass_from_dict(CaseResult, d)


@dataclass(slots=True)
class RunRecord:
    schema_version: str
    run_id: str
    created_at: str
    track: Track
    config: dict
    harnesses: list[HarnessMeta]
    cases: list  # Case (Track S) or QualityTask (Track Q)
    results: list  # CaseResult (Track S) or QualityResult (Track Q)
    aggregates: dict
    methodology: dict
    containment: dict
    scoring_version: str = SCORING_VERSION
    # cells that exceeded the time budget: SKIPPED — excluded from the aggregates above, surfaced at
    # the end of the report so a slow run never silently distorts the numbers. [{item, harness, reason}]
    skipped: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        # str-enums serialize to their value; asdict flattens nested dataclasses.
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
