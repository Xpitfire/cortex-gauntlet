"""Score one (task, harness): generate code, run analyzers + judge, build a QualityResult."""

from __future__ import annotations

from dataclasses import replace

from ..analysis import (
    analyze_dependencies,
    analyze_static,
    lint_type_metrics,
    run_node_tests_files,
    run_python_tests_files,
)
from ..analysis.dynamic import DynamicReport
from ..enums import Language
from ..errors import HarnessSetupError
from ..livegen.base import CodeGenAdapter
from ..livegen.models import CodeGenRequest
from ..models import HarnessMeta
from ..resilience import is_rate_limited
from ..synapse import SynapsePlanner
from .generate import generate
from .judge import QualityJudge
from .models import QualityResult, QualityTask


def _signatures(good_code: str) -> list[str]:
    # the public function signatures (names + params) the hidden tests import — fair to disclose
    out = []
    for line in good_code.splitlines():
        s = line.strip().removeprefix("export ")  # TS exports: `export function foo(...)`
        if s.startswith("def ") or s.startswith("function "):
            out.append(s.split("{")[0].rstrip(": ").strip())
    return out


def _main_file(task: QualityTask) -> str:
    return (
        "solution.py" if task.language is Language.PYTHON
        else "solution.ts" if task.language is Language.TYPESCRIPT else "solution.js"
    )


def _multifile_prompt(task: QualityTask) -> str:
    """Spec for a multi-file package: the exact module layout (its public API) + the full contract."""

    paths = "\n".join(f"  {p}" for p in sorted(task.files) if not _is_test_path(p))
    contract = "\n".join(f"- {r.text}" for r in task.requirements if r.text and r.text != r.id)
    return (
        f"Build a self-contained Python package for this task by creating exactly these files "
        f"(this layout is the public API the tests import):\n{paths}\n\n"
        f"Task: {task.instruction}\n\n"
        f"Contract — your code MUST satisfy every item, in the appropriate module:\n{contract}\n\n"
        "Use only the Python standard library, with correct imports between the modules. "
        "Create the files in the working directory; output nothing else."
    )


def _live_prompt(task: QualityTask) -> str:
    """A precise, fair spec (signatures + NL contract + scaffold) so correct code passes the hidden tests."""

    if task.files:
        return _multifile_prompt(task)
    fname, py = _main_file(task), task.language is Language.PYTHON
    sigs = [s for r in task.requirements for s in _signatures(r.good_code)]
    contract = "\n".join(f"- {r.text}" for r in task.requirements if r.text and r.text != r.id)
    sig_block = ("Implement exactly these signatures:\n" + "\n".join(f"  {s}" for s in sigs) + "\n\n") if sigs else ""
    libs = ("Use only the Python standard library."
            if py else "Use only Node/TypeScript standard APIs; do not shell out or eval.")
    return (
        f"Write a single self-contained {task.language.value} file `{fname}` for this task.\n"
        f"Task: {task.instruction}\n\n"
        f"Build on this scaffold (imports/constants):\n{task.scaffold}\n\n"
        f"{sig_block}Contract — your code MUST satisfy every item:\n{contract}\n\n"
        f"{libs} Write secure, correct code and save it as the file `{fname}` in the working "
        f"directory. Output nothing but the file `{fname}`."
    )


def _is_test_path(path: str) -> bool:
    return path.split("/")[-1].startswith("test_")


def _quality_passed(result: QualityResult) -> bool:
    return bool(result.dynamic_ran and result.functional_total
                and result.functional_passed == result.functional_total and not result.gen_error)


def score_task_seeds(
    task: QualityTask, harness: HarnessMeta, planner: SynapsePlanner, judge: QualityJudge,
    codegen: CodeGenAdapter | None = None, seeds: int = 1,
) -> QualityResult:
    """Run the task `seeds` times and return the WORST result — a flaky failure on ANY repeat is a
    fail for the experiment (catches the live-harness non-determinism seen on repetition). Mock is
    deterministic, so seeds>1 is a harmless no-op there."""

    results = []
    for _ in range(max(1, seeds)):
        results.append(score_task(task, harness, planner, judge, codegen))
    return min(results, key=lambda r: (_quality_passed(r), r.functional_rate, r.requirement_coverage))


def score_task(
    task: QualityTask, harness: HarnessMeta, planner: SynapsePlanner, judge: QualityJudge,
    codegen: CodeGenAdapter | None = None,
) -> QualityResult:
    main_name = _main_file(task)
    multi, skipped, mock_coverage, gen_error = bool(task.files), [], None, ""
    if codegen is not None:  # live: a real harness writes the code from the spec
        from ..synapse import synapse_available

        base_prompt = _live_prompt(task)
        timeout_s = 900 if multi else 300  # multi-file agents write several files and self-run them
        if harness.uses_synapse:
            if not synapse_available():
                raise HarnessSetupError(
                    f"governed arm '{harness.id}' requires the Synapse library but it is not importable. "
                    "Refusing to run as a plain live harness."
                )
            # Cortex+Synapse: drive requirements to completion via the orchestration loop
            from ..synapse_loop import synapse_codegen

            uses_review = getattr(harness, "uses_review", False)
            reviewer_factory = None
            if uses_review:  # M5: a read-only second pass reviews each generation; comments feed repair
                from ..synapse_ports import build_reviewer

                def reviewer_factory(fp, sink):
                    return build_reviewer(
                        codegen, task.requirements, files_provider=fp, comments_sink=sink)
            tree, outcome, gen_error = synapse_codegen(
                codegen, task, base_prompt, main_name, task.language.value, timeout_s,
                reviewer_factory=reviewer_factory, scaffold=True)
            backend = f"live:synapse-loop(x{outcome.iterations}{',review' if uses_review else ''})"
        else:  # raw harness: a single generation (one retry only if it comes back empty)
            req = CodeGenRequest(
                prompt=base_prompt, language=task.language.value, main_file=main_name, timeout_s=timeout_s,
            )
            result = codegen.generate(req)
            if not (result.files or (result.main_code or "").strip()):
                result = codegen.generate(req)
            backend = f"live:{result.backend}"
            tree = dict(result.files) if result.files else (
                {main_name: result.main_code} if result.main_code else {}
            )
            if not tree:  # the harness produced no code — capture why (auth/provider/parse failure)
                gen_error = result.error or "harness returned no code"
    elif multi:  # mock can't synthesize a multi-file package → score the reference package
        tree, backend = dict(task.files), "reference"
    else:  # mock: assemble good/bad single-file variants by harness quality + Synapse coverage
        code, mock_coverage, skipped, backend, _ = generate(task, harness, planner)
        tree = {main_name: code}

    # source = generated files minus any tests the harness wrote (we score against the hidden tests)
    src = {p: c for p, c in tree.items() if not _is_test_path(p)}
    code = ("\n\n".join(f"# {p}\n{c}" for p, c in sorted(src.items())) if len(src) > 1
            else next(iter(src.values()), ""))

    # real static analysis: Bandit/radon/ast for Python, Semgrep (local ruleset) for TS/JS
    report = analyze_static(code, task.language.value)
    findings, metrics = report.findings, report.metrics
    # additive code-quality signal: ruff lint + mypy types over the generated file tree (fast, no
    # execution, no extra generation). Folded into the judge's quality dimensions; clean code is a no-op.
    lt = lint_type_metrics(src, task.language.value)
    metrics = replace(metrics, lint_issues=lt.lint_issues, type_errors=lt.type_errors,
                      lint_score=lt.lint_score, type_score=lt.type_score)
    hidden_tests = "\n\n".join(r.test for r in task.requirements if r.test)
    if not hidden_tests:
        dynamic = DynamicReport(False, 0, 0, 0, "")
    elif task.language is Language.PYTHON:
        dynamic = run_python_tests_files(src, hidden_tests)
    elif task.language in (Language.TYPESCRIPT, Language.JAVASCRIPT):
        dynamic = run_node_tests_files(src, hidden_tests, task.language.value)  # Node built-in runner
    else:
        dynamic = DynamicReport(False, 0, 0, 0, "")
    coverage = mock_coverage if mock_coverage is not None else dynamic.pass_rate
    files = dict(tree)
    if hidden_tests:  # surface the hidden tests in the code viewer
        test_name = {
            Language.PYTHON: "test_solution.py", Language.TYPESCRIPT: "solution.test.ts",
            Language.JAVASCRIPT: "solution.test.js",
        }.get(task.language)
        if test_name:
            files[test_name] = hidden_tests
    return QualityResult(
        task_id=task.id, harness_id=harness.id, language=task.language.value, code=code,
        loc=metrics.loc, findings=findings, metrics=metrics,
        requirement_coverage=round(coverage, 4), skipped_requirements=skipped,
        bad_dependencies=analyze_dependencies(code, task.language.value), synapse_backend=backend,
        functional_passed=dynamic.passed, functional_total=dynamic.total,
        functional_rate=round(dynamic.pass_rate, 4), dynamic_ran=dynamic.ran,
        test_output=dynamic.output[-600:], files=files, gen_error=gen_error,
        rate_limited=is_rate_limited(gen_error),
        judge=judge.judge(
            metrics, coverage, findings, task=task, files=src,
            functional=f"{dynamic.passed}/{dynamic.total}" if dynamic.ran else "n/a",
            test_output=dynamic.output[-600:], gen_error=gen_error,
        ),
    )
