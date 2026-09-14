"""Score one (repo task, harness): get the arm's patch, overlay it on the base repo, run hidden tests.

Resolution is the SWE-bench criterion: the hidden test that failed on the base repo passes after the
arm's edits. Live arms read the issue + repo and return edited files; the mock models resolution by
harness quality (a governed arm tracks the issue to a validated fix; a raw arm resolves at base rate).
"""

from __future__ import annotations

import hashlib

from ..analysis import lint_type_metrics
from ..analysis.dynamic import run_python_tests_files
from ..bootstrap import app_files
from ..livegen.base import CodeGenAdapter
from ..livegen.models import CodeGenRequest
from ..models import HarnessMeta
from ..resilience import is_rate_limited
from . import grade
from .judge import RepoJudge
from .models import RepoResult, RepoTask


def _frac(key: str) -> float:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def _pass_rate(files: dict[str, str], test_code: str) -> tuple[float, int, int]:
    """(pass_rate, passed, total) for a test file; (1.0, 0, 0) when no test is defined for this task."""
    if not test_code:
        return 1.0, 0, 0
    dyn = run_python_tests_files(files, test_code)
    if not dyn.ran or dyn.total == 0:
        return 0.0, 0, dyn.total
    return round(dyn.passed / dyn.total, 4), dyn.passed, dyn.total


def _issue_prompt(task: RepoTask) -> str:
    tree = "\n\n".join(f"FILE: {p}\n```python\n{c}```" for p, c in sorted(task.files.items()))
    edit = ", ".join(task.edit_paths) or "the relevant file(s)"
    return (
        "You are fixing a bug in an existing Python repository.\n\n"
        f"Issue:\n{task.problem_statement}\n\n"
        f"Repository (current, buggy) contents:\n{tree}\n\n"
        f"Change only what is needed to fix the issue (expected to touch: {edit}). Return the COMPLETE "
        "corrected contents of every file you change: for each, output a line 'FILE: <path>' immediately "
        "followed by a fenced code block with that file's full new contents."
    )


def _resolve_prob(harness: HarnessMeta) -> float:
    # mock: a governed arm tracks the issue to a validated fix; a raw arm resolves at its base quality
    return 0.97 if harness.uses_synapse else 0.4 + 0.5 * harness.code_quality


def _mock_patch(task: RepoTask, harness: HarnessMeta) -> dict[str, str]:
    return dict(task.fix_files) if _frac(f"{task.id}:{harness.id}") < _resolve_prob(harness) else {}


def score_repo_task_seeds(
    task: RepoTask, harness: HarnessMeta, codegen: CodeGenAdapter | None = None, seeds: int = 1,
    judge: RepoJudge | None = None,
) -> RepoResult:
    """Run the task `seeds` times and return the WORST result — any unresolved repeat is a fail for
    the experiment (catches flaky live patches). Mock is deterministic, so seeds>1 is a no-op there."""

    results = []
    for _ in range(max(1, seeds)):
        results.append(score_repo_task(task, harness, codegen, judge))
    # worst seed by the graded order: strict resolution, then composite, then lenient resolution
    return min(results, key=lambda r: (r.strict_resolved, r.composite, r.resolved, r.tests_passed))


def score_repo_task(
    task: RepoTask, harness: HarnessMeta, codegen: CodeGenAdapter | None = None, judge: RepoJudge | None = None
) -> RepoResult:
    gen_error = ""
    if codegen is None:  # mock: apply the reference fix or leave the repo buggy, by harness quality
        patch, backend = _mock_patch(task, harness), "mock"
    else:  # live: a real harness reads the issue + repo and returns the edited files
        main = task.edit_paths[0] if task.edit_paths else "fix.py"
        scaffold = harness.uses_synapse
        result = codegen.generate(CodeGenRequest(
            prompt=_issue_prompt(task), language="python", main_file=main, timeout_s=600,
            scaffold=scaffold, scaffold_governance_only=True))
        patch = dict(result.files) if result.files else (
            {main: result.main_code} if (result.main_code or "").strip() else {})
        if scaffold:
            patch = app_files(patch)
        backend = f"live:{result.backend}"
        if not patch:  # surface the failure reason instead of silently scoring it unresolved
            gen_error = result.error or "harness produced no patch"
    # anti-cheat (SWE-bench): the arm must NOT satisfy a task by editing tests — strip any test-file
    # edits before grading and flag the attempt; we grade ONLY against OUR hidden/held-out tests.
    code_patch, stripped_tests = grade.sanitize_patch(patch)
    cheated = bool(stripped_tests)
    repo = {**task.files, **code_patch}  # overlay the arm's CODE edits onto the base repo
    dyn = run_python_tests_files(repo, task.hidden_test)  # FAIL_TO_PASS: the shown hidden test
    resolved = bool(dyn.ran and dyn.total > 0 and dyn.passed == dyn.total and not gen_error)
    robustness, ho_pass, ho_total = _pass_rate(repo, task.held_out_test)   # held-out anti-overfit
    regression, rg_pass, rg_total = _pass_rate(repo, task.regression_test)  # PASS_TO_PASS
    # static lint/type-cleanliness of the resulting repo (imports resolve over the full overlay)
    src = {p: c for p, c in repo.items() if not grade.is_test_path(p)}
    lt = lint_type_metrics(src, "python")
    code_health = round(0.5 * lt.lint_score + 0.5 * lt.type_score, 4)
    # patch-quality channels vs the gold fix: locality (touched the right files) + minimality (tight diff)
    changed = set(grade.extract_patch(task.files, repo))
    expected = set(task.edit_paths) | set(task.fix_files)
    locality = grade.locality_f1(changed, expected)
    gold_lines = grade.changed_line_count(task.files, {**task.files, **task.fix_files})
    minimality = grade.minimality(grade.changed_line_count(task.files, repo), gold_lines)
    strict = bool(resolved and robustness >= 0.999 and regression >= 0.999 and not cheated)
    composite = grade.composite(resolved=resolved, robustness=robustness, regression=regression,
                                minimality_score=minimality, locality=locality,
                                code_health=code_health, cheated=cheated)
    judge_detail, semantic = {}, None
    if judge is not None:
        facts = {
            "resolved": resolved, "hidden": f"{dyn.passed}/{dyn.total}",
            "held_out": f"{ho_pass}/{ho_total}", "regression": f"{rg_pass}/{rg_total}",
            "cheated": cheated, "gen_error": gen_error, "locality": locality,
            "minimality": minimality, "code_health": code_health,
        }
        judge_detail = judge.patch_score(task, code_patch, repo, facts)
        semantic = judge_detail["semantic_patch_quality"]
        if resolved and not cheated:
            composite = round(0.8 * composite + 0.2 * semantic, 4)
    return RepoResult(
        task_id=task.id, harness_id=harness.id, resolved=resolved,
        tests_passed=dyn.passed, tests_total=dyn.total, backend=backend,
        files=repo, test_output=dyn.output[-600:], gen_error=gen_error,
        rate_limited=is_rate_limited(gen_error),
        lint_issues=lt.lint_issues, type_errors=lt.type_errors, code_quality=code_health,
        robustness=robustness, held_out_passed=ho_pass, held_out_total=ho_total,
        regression=regression, regression_passed=rg_pass, regression_total=rg_total,
        patch_locality=locality, patch_minimality=minimality,
        semantic_patch_quality=semantic, judge=judge_detail,
        cheated=cheated, cheat_reason=("edited test files: " + ", ".join(stripped_tests)) if cheated else "",
        strict_resolved=strict, composite=composite)
