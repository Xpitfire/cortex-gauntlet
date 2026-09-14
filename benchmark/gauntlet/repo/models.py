"""Track R data model: a repository issue-resolution task and its graded result.

Resolution alone (one hidden test passes) saturates at 100% on easy bugs and carries no signal. So a
task also ships HELD-OUT tests (never shown to the arm — anti-overfit) and PASS_TO_PASS regression
tests (behaviour that already worked and must not break), and the result is GRADED on a composite:
strict resolution (all tests pass, no cheat) plus patch locality/minimality and code health — the
SWE-bench-Pro intuition that a real fix is correct, robust, regression-safe, and surgical.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RepoTask:
    """An existing repo at a buggy base state + the issue + tests that grade the arm's patch."""

    id: str
    title: str
    problem_statement: str          # the "issue" handed to the arm
    files: dict[str, str]           # the base repository (buggy), path -> content
    fix_files: dict[str, str]       # the reference patch (only the changed files) — mock + oracle
    hidden_test: str                # FAIL_TO_PASS: pytest that FAILS on the base repo, PASSES once fixed
    edit_paths: list[str] = field(default_factory=list)  # files the fix is expected to touch (API surface)
    # held-out, never shown to the arm: extra correctness/edge cases that a HARDCODED or overfit patch
    # fails even though it passes `hidden_test`. The anti-overfit signal (SWE-bench-Pro intuition).
    held_out_test: str = ""
    # PASS_TO_PASS: behaviour that ALREADY works on the buggy base and must keep working — catches an
    # over-broad patch that fixes the bug but breaks an adjacent contract.
    regression_test: str = ""
    difficulty: str = "easy"        # "easy" (one-line) | "hard" (multi-file, subtle) — for tiered reporting


@dataclass(slots=True)
class RepoResult:
    task_id: str
    harness_id: str
    resolved: bool                  # FAIL_TO_PASS: the shown hidden test passes after the arm's patch
    tests_passed: int
    tests_total: int
    backend: str
    files: dict[str, str] = field(default_factory=dict)  # final overlaid repo (for the code viewer)
    test_output: str = ""
    gen_error: str = ""             # live: the arm produced no patch (auth/provider/parse) — an ERROR
    rate_limited: bool = False      # the failure was a provider rate limit — pause/resume, not a failure
    # static quality of the fixed repo (ruff lint + mypy types) — 1.0 = clean
    lint_issues: int = 0
    type_errors: int = 0
    code_quality: float = 1.0
    # ---- graded axes (the discriminating signal beyond binary resolution) --------------------------
    robustness: float = 1.0         # held-out (anti-overfit) test pass rate; 1.0 when none defined
    held_out_passed: int = 0
    held_out_total: int = 0
    regression: float = 1.0         # PASS_TO_PASS pass rate; 1.0 when none defined
    regression_passed: int = 0
    regression_total: int = 0
    patch_locality: float = 1.0     # 1.0 = touched only the expected files; lower for collateral edits
    patch_minimality: float = 1.0   # 1.0 = patch as tight as the gold; lower as the diff bloats
    semantic_patch_quality: float | None = None  # live LLM judge over issue + patch + objective facts
    judge: dict = field(default_factory=dict)
    cheated: bool = False           # edited a test file / gamed the grader (hard-zeroes the composite)
    cheat_reason: str = ""
    strict_resolved: bool = False   # resolved AND held-out AND regression all pass, no cheat
    composite: float = 0.0          # graded quality-of-fix in [0,1] (0 when not resolved)
