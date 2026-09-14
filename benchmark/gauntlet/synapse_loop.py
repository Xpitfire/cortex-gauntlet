"""Synapse-driven generate → validate → repair loop for live Cortex harnesses.

Wraps a code-gen adapter in the real Synapse `Orchestrator`: plan the task's requirements, then on
each pass generate, observe which requirements are evidenced (spec-derived markers — NEVER the hidden
tests), validate, and re-prompt to repair the gaps until complete or progress stalls. This is the
long-horizon "track to completion" behaviour that separates Cortex+Synapse from one raw generation:
raw harnesses generate once; Cortex iterates until the contract is satisfied.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from synapse import (
    BeliefStateController,
    CompletionJudge,
    OrchestrationContext,
    OrchestrationResult,
    Orchestrator,
)
from synapse.domain.contracts import EvidenceRef, ExecutionObservation
from synapse.domain.requirements import Requirement, RequirementKind, RequirementSet

from .bootstrap import app_files
from .livegen.base import CodeGenAdapter
from .livegen.models import CodeGenRequest
from .quality.models import QualityTask
from .quality_gate import GateResult, run_quality_gate


def _requirement_set(task: QualityTask) -> RequirementSet:
    return RequirementSet(
        instruction=task.instruction,
        requirements=[
            Requirement(id=r.id, text=r.text, kind=RequirementKind(r.kind), required=r.required)
            for r in task.requirements
        ],
    )


def _concat(files: dict[str, str]) -> str:
    if len(files) == 1:
        return next(iter(files.values()))
    return "\n\n".join(f"# {path}\n{body}" for path, body in sorted(files.items()))


# Governance directives the Synapse loop adds on top of the raw brief. They are GENERAL engineering
# hygiene (not task-specific): they target the two failure modes seen on raw harnesses in live runs —
# "no file produced" (the agent prints prose/explanation instead of writing code) and ModuleNotFound
# (the agent imports a package/module that is not installed and that it never creates). Keeping these
# in the loop (not in a hook or a per-test string) is exactly the Cortex value the benchmark measures.
_RUNNABLE_PREAMBLE = (
    "\n\nDeliver a COMPLETE, SELF-CONTAINED, RUNNABLE solution:\n"
    "- Write the actual file(s) — output the full contents of every file the solution needs; never "
    "stop at a description, plan, or partial snippet.\n"
    "- Depend only on the language's STANDARD LIBRARY plus modules you define in this same solution. "
    "Do NOT import third-party packages that may not be installed; if a capability is needed, implement "
    "it with the standard library.\n"
    "- Every module/name you import must exist: if you split code across files, create EVERY file you "
    "import from, and make sure the entry point imports and runs cleanly with no ModuleNotFoundError.\n"
    "- Also write thorough tests covering EACH requirement, named so the runner finds them "
    "(test_*.py for Python; *.test.ts / *.test.js for TypeScript/JavaScript); the solution must pass "
    "them and be free of lint/syntax/compile errors."
)


def _observe(task: QualityTask, files: dict[str, str], gate: GateResult) -> ExecutionObservation:
    """Deliverable/constraint reqs need their spec marker; verification reqs need the quality gate to pass."""

    code = _concat(files)
    completed: set[str] = set()
    for requirement in task.requirements:
        if RequirementKind(requirement.kind) is RequirementKind.VERIFICATION:
            satisfied = gate.passed
        else:
            satisfied = not requirement.evidence or requirement.evidence in code
        if satisfied:
            completed.add(requirement.id)
    return ExecutionObservation(
        completed_requirement_ids=completed,
        satisfied_expectation_ids={f"exp-{rid}" for rid in completed},
        evidence=[EvidenceRef(id=f"ev-{rid}", kind="symbol", locator=f"req:{rid}") for rid in completed],
    )


def _repair_prompt(
    base_prompt: str, task: QualityTask, open_ids: set[str], files: dict[str, str], gate: GateResult,
    review_comments: list[str] | None = None,
) -> str:
    missing = [r.text for r in task.requirements if r.id in open_ids]
    body = f"{base_prompt}{_RUNNABLE_PREAMBLE}\n\nYour previous attempt is not yet complete."
    if missing:
        body += "\n\nThese requirements are not yet satisfied:\n" + "\n".join(f"- {text}" for text in missing)
    if not gate.passed:
        body += f"\n\nYour self-check failed ({gate.summary}). Fix the code and tests."
    if review_comments:  # the read-only reviewer's feedback from the previous pass, to address now
        body += "\n\nReviewer feedback to address:\n" + "\n".join(f"- {c}" for c in review_comments)
    return (
        body + "\n\nYour current code:\n```\n" + _concat(files)
        + "\n```\n\nReturn the COMPLETE corrected solution that satisfies ALL requirements."
    )


def synapse_codegen(
    codegen: CodeGenAdapter, task: QualityTask, base_prompt: str, main_file: str,
    language: str, timeout_s: int, max_iterations: int = 3,
    reviewer_factory: Callable[[Callable[[], dict[str, str]], dict[str, Any]], CompletionJudge]
    | None = None,
    scaffold: bool = False,
) -> tuple[dict[str, str], OrchestrationResult, str]:
    """Run the Synapse orchestration loop around a code-gen adapter; return (files, outcome, error).
    `error` is the last underlying codegen failure reason, surfaced when no code was ever captured.

    When `reviewer_factory` is given, a read-only `CompletionJudge` reviews each generation: its
    comments flow into the repair prompt and a `BeliefStateController` consults it to decide completion.
    Without it the loop is byte-identical to the original `Orchestrator(max_iterations)` path."""

    requirements = _requirement_set(task)
    first_prompt = base_prompt + _RUNNABLE_PREAMBLE
    state: dict[str, dict[str, str]] = {"files": {}}
    gate_state: dict[str, GateResult] = {"gate": GateResult(False, False, False, False, "no run")}
    errbox = {"msg": ""}
    review_box: dict[str, Any] = {"comments": []}

    reviewing = reviewer_factory is not None

    def execute(context: OrchestrationContext) -> ExecutionObservation:
        open_ids = set(context.open_requirement_ids())
        # only thread review feedback when a reviewer is active; the no-reviewer repair prompt never
        # touches review state, so that path stays byte-identical to the original loop independently
        # of the (empty) review_box.
        review_comments = review_box["comments"] if reviewing else None
        prompt = (
            first_prompt if context.iteration == 1
            else _repair_prompt(base_prompt, task, open_ids, state["files"], gate_state["gate"],
                                review_comments)
        )
        result = codegen.generate(
            CodeGenRequest(
                prompt=prompt, language=language, main_file=main_file, timeout_s=timeout_s,
                scaffold=scaffold, scaffold_governance_only=True,
            )
        )
        files = dict(result.files) if result.files else (
            {main_file: result.main_code} if (result.main_code or "").strip() else {}
        )
        if scaffold:
            files = app_files(files)
        if files:  # keep the last non-empty generation (a transient empty must not erase progress)
            state["files"] = files
        else:  # remember why this pass produced nothing, for diagnostics if every pass fails
            errbox["msg"] = result.error or "harness returned no code"
        gate_state["gate"] = (run_quality_gate(state["files"], language=language)
                               if state["files"] else gate_state["gate"])
        return _observe(task, state["files"], gate_state["gate"])

    if reviewing:  # activate the review inner-loop (belief-driven completion)
        reviewer = reviewer_factory(lambda: state["files"], review_box)
        orchestrator = Orchestrator(
            max_iterations=max_iterations,
            completion_controller=BeliefStateController(), judges=[reviewer],
        )
    else:  # no reviewer: the original path, byte-identical
        orchestrator = Orchestrator(max_iterations=max_iterations)
    outcome = orchestrator.run(requirements, execute)
    return state["files"], outcome, (errbox["msg"] if not state["files"] else "")
