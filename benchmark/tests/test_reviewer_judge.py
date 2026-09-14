"""M5 review inner-loop: the read-only CortexReviewerJudge, its prompt/parse, and the synapse_codegen
wiring. Hermetic — NO network, NO live CLI (the live CLI review path needs auth/tokens and is not run)."""

from __future__ import annotations

import pytest

pytest.importorskip("synapse.adapters.lifecycle.ports")

from gauntlet.enums import Language
from gauntlet.livegen.models import CodeGenRequest, CodeGenResult
from gauntlet.quality.models import QualityTask, RequirementSpec
from gauntlet.synapse_loop import _RUNNABLE_PREAMBLE, synapse_codegen
from gauntlet.synapse_ports import build_reviewer  # noqa: F401 — exercised below
from gauntlet.synapse_ports.reviewer_judge import (
    CortexReviewerJudge,
    ReviewReport,
    format_review_prompt,
    parse_review_reply,
)


# --- a fake synapse JudgeContext (assess never reads it) ---------------------------------------
class _Ctx:
    iteration = 1


def _reqs():
    # distinctive .text/.id (must appear in the prompt) AND distinctive hidden .test/.good_code/.bad_code
    # (must NEVER appear in the prompt).
    return [
        RequirementSpec(
            id="REQ_ALPHA", text="REVIEWABLE_REQUIREMENT_TEXT must hold",
            kind="goal", category="tests",
            good_code="SECRET_GOOD_CODE_SNIPPET = 1",
            bad_code="SECRET_BAD_CODE_SNIPPET = 2",
            test="def test_HIDDEN_GROUND_TRUTH(): assert SECRET_HIDDEN_TEST",
            evidence="marker_alpha",
        ),
    ]


# --- format_review_prompt: the critical scoring-integrity test --------------------------------
def test_format_review_prompt_excludes_hidden_tests_and_solutions():
    files = {"solution.py": "def f():\n    return 1\n"}
    prompt = format_review_prompt(files, _reqs())
    # the reviewer SEES requirement id + text and the code under review
    assert "REQ_ALPHA" in prompt
    assert "REVIEWABLE_REQUIREMENT_TEXT must hold" in prompt
    assert "def f()" in prompt
    # the reviewer NEVER sees the hidden ground truth
    assert "SECRET_HIDDEN_TEST" not in prompt
    assert "test_HIDDEN_GROUND_TRUTH" not in prompt
    assert "SECRET_GOOD_CODE_SNIPPET" not in prompt
    assert "SECRET_BAD_CODE_SNIPPET" not in prompt
    # it is told to return JSON and to NOT write files
    assert "JSON" in prompt and "approved" in prompt
    assert "read-only" in prompt or "Do NOT" in prompt


# --- parse_review_reply -----------------------------------------------------------------------
def test_parse_review_reply_valid_json():
    out = (
        'some log line\n{"approved": false, "comments": '
        '[{"requirement_id": "REQ_ALPHA", "severity": "high", "comment": "fix the SQL"}]}\ntrailer'
    )
    report = parse_review_reply(out)
    assert isinstance(report, ReviewReport)
    assert report.approved is False
    assert report.comments and "fix the SQL" in report.comments[0]
    assert "REQ_ALPHA" in report.comments[0]


def test_parse_review_reply_approved():
    report = parse_review_reply('{"approved": true, "comments": []}')
    assert report.approved is True


def test_parse_review_reply_garbage_never_silent_approves():
    report = parse_review_reply("this is not json at all, totally garbage output")
    assert report.approved is False  # DEFAULT TO NOT APPROVED on any failure
    assert report.raw  # raw output captured for diagnostics


def test_parse_review_reply_empty_never_silent_approves():
    report = parse_review_reply("")
    assert report.approved is False


# --- CortexReviewerJudge.assess ---------------------------------------------------------------
def test_assess_approved_is_complete_and_stashes_comments():
    sink: dict = {}
    files = {"solution.py": "x = 1\n"}
    judge = CortexReviewerJudge(
        lambda f, r: ReviewReport(approved=True, comments=["c1", "c2"], summary="ok"),
        _reqs(), files_provider=lambda: files, comments_sink=sink,
    )
    verdict = judge.assess(_Ctx())
    from synapse import CompletionLabel, JudgeModality

    assert verdict.label is CompletionLabel.COMPLETE
    assert verdict.modality is JudgeModality.TEXT
    assert sink["comments"] == ["c1", "c2"]


def test_assess_not_approved_is_partial():
    judge = CortexReviewerJudge(
        lambda f, r: ReviewReport(approved=False, comments=["redo"], summary="nope"),
        _reqs(), files_provider=lambda: {"solution.py": "x = 1\n"},
    )
    from synapse import CompletionLabel

    assert judge.assess(_Ctx()).label is CompletionLabel.PARTIAL


def test_assess_empty_files_is_poor_and_never_calls_review():
    called = {"n": 0}

    def review_fn(f, r):
        called["n"] += 1
        return ReviewReport(approved=True)

    judge = CortexReviewerJudge(review_fn, _reqs(), files_provider=lambda: {})
    from synapse import CompletionLabel

    assert judge.assess(_Ctx()).label is CompletionLabel.POOR
    assert called["n"] == 0  # no files → never invoke the (potentially live) reviewer


# --- recording fake codegen + synapse_codegen wiring ------------------------------------------
class _RecordingCodeGen:
    """A deterministic codegen that records every prompt it is handed (to assert review feedback flows)."""

    binary_name = "codex"

    def __init__(self, meta=None) -> None:
        self.meta = meta
        self.prompts: list[str] = []

    def generate(self, request: CodeGenRequest) -> CodeGenResult:
        self.prompts.append(request.prompt)
        # always satisfy the requirement's spec marker so the deterministic verdict alone never blocks
        code = "marker_alpha = True\n\n\ndef test_alpha():\n    assert marker_alpha\n"
        return CodeGenResult(
            backend="rec", main_code=code, files={request.main_file: code}, ok=True,
        )


def _task():
    return QualityTask(
        id="rev_task", title="Reviewable", language=Language.PYTHON,
        instruction="do the thing", scaffold="", requirements=_reqs(),
    )


def _approve_after(n: int):
    """A reviewer factory whose reviewer approves only from the n-th review onward (PARTIAL before)."""
    calls = {"n": 0}

    def factory(files_provider, sink):
        def review_fn(files, requirements):
            calls["n"] += 1
            if calls["n"] >= n:
                return ReviewReport(approved=True, comments=[], summary="approved")
            return ReviewReport(
                approved=False, comments=[f"REVIEW_FIX_ROUND_{calls['n']}"], summary="needs work",
            )

        return CortexReviewerJudge(
            review_fn, requirements=[], files_provider=files_provider, comments_sink=sink,
        )

    return factory, calls


def test_synapse_codegen_review_comments_flow_into_repair_prompt():
    codegen = _RecordingCodeGen()
    factory, calls = _approve_after(3)  # not approved on passes 1 & 2 → drives repair prompts
    files, outcome, error = synapse_codegen(
        codegen, _task(), base_prompt="BASE", main_file="solution.py",
        language="python", timeout_s=10, max_iterations=4, reviewer_factory=factory,
    )
    assert files and not error
    assert outcome.iterations >= 2  # the reviewer kept the loop going past one shot
    assert calls["n"] >= 1  # the reviewer was consulted
    # the first review's comment must appear in a later generation's prompt (feedback flowed back)
    later_prompts = "\n".join(codegen.prompts[1:])
    assert "REVIEW_FIX_ROUND_1" in later_prompts
    assert "Reviewer feedback to address:" in later_prompts


def test_synapse_codegen_without_reviewer_is_unchanged():
    codegen = _RecordingCodeGen()
    files, outcome, error = synapse_codegen(
        codegen, _task(), base_prompt="BASE", main_file="solution.py",
        language="python", timeout_s=10, max_iterations=4,
    )
    assert files and not error
    # the no-reviewer first prompt is exactly the base brief + runnable preamble (byte-identical)
    assert codegen.prompts[0] == "BASE" + _RUNNABLE_PREAMBLE
    # no reviewer factory → no review feedback section ever appears in any prompt
    assert all("Reviewer feedback to address:" not in p for p in codegen.prompts)
