"""Additive static-quality metrics (ruff + mypy) and the import-resolution gate.

Covers req #3 (general fix for ModuleNotFound / no-file via the Synapse-loop directive + a static
import gate) and req #4 (additive ruff/mypy quality metrics folded into the quality aspect).
"""

from gauntlet.analysis import lint_type_metrics
from gauntlet.analysis.models import CodeMetrics
from gauntlet.quality.judge import HeuristicQualityJudge
from gauntlet.quality_gate import _unresolved_imports, run_quality_gate

_CLEAN = {"solution.py": "def add(a: int, b: int) -> int:\n    return a + b\n"}
_DIRTY = {"solution.py": "import os\nimport requestz\nx=1\ndef f( ):\n  y=2\n  return undefined\n"}


def test_clean_python_scores_perfect_and_is_a_noop():
    r = lint_type_metrics(_CLEAN)
    assert r.ran and r.lint_issues == 0 and r.type_errors == 0
    assert r.lint_score == 1.0 and r.type_score == 1.0


def test_dirty_python_is_penalised_by_both_lint_and_types():
    r = lint_type_metrics(_DIRTY)
    assert r.lint_issues > 0 and r.type_errors >= 1  # mypy needs --check-untyped-defs to see `undefined`
    assert r.lint_score < 1.0 and r.type_score < 1.0


def test_typescript_clean_scores_perfect():
    # Exercise the pinned JS/TS toolchain; absent analyzers are unavailable, never clean.
    r = lint_type_metrics({"a.ts": 'export const greeting: string = "hi";\n'}, "typescript")
    assert r.lint_score == 1.0 and r.type_score == 1.0


def test_typescript_type_error_is_penalised_when_tsc_available():
    import shutil
    from pathlib import Path

    import pytest
    if shutil.which("tsc") is None and not (Path(__file__).resolve().parents[1]
                                            / "node_modules" / ".bin" / "tsc").exists():
        pytest.skip("tsc not installed")
    r = lint_type_metrics({"a.ts": 'const x: number = "oops";\n'}, "typescript")
    assert r.type_errors >= 1 and r.type_score < 1.0


def test_unresolved_import_is_caught_statically():
    files = {"app.py": "import os\nimport requestz\nfrom util import h\n", "util.py": "def h():\n    return 1\n"}
    # requestz is neither stdlib, installed, nor local; os/util resolve
    assert _unresolved_imports(files) == ["requestz"]


def test_quality_gate_fails_and_surfaces_a_modulenotfound():
    gate = run_quality_gate({"app.py": "import requestz\n\n\ndef f():\n    return requestz.go()\n"})
    assert gate.imports_ok is False and gate.passed is False
    assert "unresolved imports" in gate.summary and "requestz" in gate.summary


def test_quality_gate_imports_ok_when_everything_resolves():
    gate = run_quality_gate({"app.py": "import json\nfrom util import h\n", "util.py": "def h():\n    return 1\n"})
    assert gate.imports_ok is True


def _metrics(lint_score: float, type_score: float) -> CodeMetrics:
    return CodeMetrics(loc=20, complexity=4, functions=2, duplication_pct=0.0, comment_ratio=0.1,
                       has_tests=True, has_error_handling=True, lint_score=lint_score, type_score=type_score)


def test_judge_clean_code_is_unchanged_dirty_code_is_penalised():
    judge = HeuristicQualityJudge()
    clean = judge.judge(_metrics(1.0, 1.0), coverage=1.0, findings=[])
    dirty = judge.judge(_metrics(0.4, 0.4), coverage=1.0, findings=[])
    # lint hits readability; types hit architecture + interface — strictly worse, never better
    assert dirty["readability"] < clean["readability"]
    assert dirty["architecture"] < clean["architecture"]
    assert dirty["interface"] < clean["interface"]



# ---- categorized, test-counted success (req: don't misrepresent 6/7 as a total failure) -----------
from gauntlet.checks import checks_block  # noqa: E402
from gauntlet.quality.metrics import check_breakdown  # noqa: E402


def _qresult(passed, total, lint=1.0, typ=1.0, findings=(), lang="python", harness_id="codex_cli_raw"):
    from gauntlet.analysis.models import CodeMetrics
    from gauntlet.quality.models import QualityResult
    m = CodeMetrics(loc=20, complexity=4, functions=2, duplication_pct=0.0, comment_ratio=0.1,
                    has_tests=True, has_error_handling=True, lint_score=lint, type_score=typ)
    return QualityResult(task_id="t", harness_id=harness_id, language=lang, code="x", loc=20,
        findings=list(findings), metrics=m, requirement_coverage=0.86, skipped_requirements=[],
        bad_dependencies=[], synapse_backend="live:synapse-loop(x1)", functional_passed=passed,
        functional_total=total, functional_rate=passed / total, dynamic_ran=True)


def test_check_breakdown_categorizes_functionality_quality_security():
    # the screenshot case: 6/7 functional, clean lint/types, no vulns
    br = check_breakdown(_qresult(6, 7))
    assert br["functionality"] == {"passed": 6.0, "total": 7.0}
    assert br["quality"] == {"passed": 2.0, "total": 2.0}       # ruff + mypy = 2 clean checks
    assert br["security"] == {"passed": 1.0, "total": 1.0}      # no findings


def test_six_of_seven_reads_as_ninety_percent_not_total_failure():
    block = checks_block({"functionality": (6.0, 7.0), "quality": (2.0, 2.0), "security": (1.0, 1.0)})
    assert block["overall"]["rate"] == 0.9                       # 9/10, NOT a binary 0% FAIL
    assert block["functionality"]["rate"] == round(6 / 7, 4)


def test_quality_aggregate_exposes_categorized_checks():
    from gauntlet.quality.aggregate import aggregate_quality
    from gauntlet.run import PRESETS
    h = PRESETS["codex_cli_raw"]
    agg = aggregate_quality([], [_qresult(6, 7, findings=[])], [h])
    checks = agg["per_harness"]["codex_cli_raw"]["checks"]
    assert checks["overall"]["rate"] == 0.9
    assert set(checks) == {"functionality", "quality", "security", "overall"}


def test_project_code_health_penalizes_lint_and_type_errors():
    from gauntlet.project.score import _code_health

    clean = {"app.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
             "test_app.py": "def test_add():\n    assert True\n"}
    dirty = {"app.py": "import requestz\nx=1\ndef f( ):\n  return missing\n",
             "test_app.py": "def test_placeholder():\n    assert True\n"}
    assert _code_health(clean, 0) > _code_health(dirty, 0)


def test_quality_report_renders_the_categorized_success_block():
    import json
    import tempfile
    from pathlib import Path

    from gauntlet.quality.run import run_quality_suite
    from gauntlet.report import build_report
    rec = run_quality_suite(limit=2)
    with tempfile.TemporaryDirectory() as tmp:
        html = build_report(json.loads(rec.to_json()), Path(tmp) / "report.html")
    assert "overall success (per-check)" in html and "functionality (pytest)" in html
