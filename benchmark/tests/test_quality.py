"""Track Q: corpus, SAST/deps/metrics analyzers, Synapse-driven quality delta, report."""

import json

from gauntlet.quality.corpus import load_quality_tasks
from gauntlet.quality.metrics import analyze, smell_count
from gauntlet.quality.run import run_quality_suite
from gauntlet.quality.sast import scan_code, scan_dependencies
from gauntlet.report import build_report


def test_corpus_loads_tasks_with_requirements():
    tasks = load_quality_tasks()
    assert tasks and all(t.requirements for t in tasks)
    langs = {t.language.value for t in tasks}
    assert {"python", "typescript"} <= langs  # runnable Python + Semgrep-analyzed TypeScript
    assert any(r.test for t in tasks for r in t.requirements)  # hidden ground-truth tests present


def test_sast_flags_known_vulnerable_snippets():
    cwes = {f.cwe for f in scan_code(
        'cur.execute("SELECT * FROM t WHERE n=\'" + n + "\'")\n'
        "digest = hashlib.md5(p).hexdigest()\n"
        "os.system(cmd + arg)\n"
        "requests.get(u, verify=False)\n"
        "count = eval(value)\n"
    )}
    assert {"CWE-89", "CWE-327", "CWE-78", "CWE-295", "CWE-95"} <= cwes


def test_sast_clean_on_safe_code():
    assert scan_code('cur.execute("SELECT * FROM t WHERE n=%s", (n,))\nx = int(value)\n') == []


def test_dependency_scan_flags_hallucinated_package():
    assert "secure_utils_pro" in scan_dependencies("import secure_utils_pro\nimport json\n")
    assert scan_dependencies("import json\nimport os\n") == []


def test_metrics_detect_tests_and_error_handling():
    m = analyze("def test_x():\n    try:\n        run()\n    except Exception:\n        pass\n")
    assert m.has_tests and m.has_error_handling and smell_count(m) < 5


def test_synapse_lifts_coverage_and_quality_vs_raw():
    agg = run_quality_suite().aggregates
    ph = agg["per_harness"]
    raw, syn = "codex_cli_raw", "cortex_wrapped"
    assert ph[syn]["requirement_coverage"] > ph[raw]["requirement_coverage"]
    assert ph[syn]["functional_rate"] > ph[raw]["functional_rate"]  # real pytest pass-rate
    assert ph[syn]["vulns_per_task"] <= ph[raw]["vulns_per_task"]
    assert ph[syn]["maintainability"]["debt"] < ph[raw]["maintainability"]["debt"]
    assert agg["synapse_delta"]["requirement_coverage"]["delta"] > 0
    assert agg["synapse_delta"]["functional_rate"]["delta"] > 0


def test_dynamic_analysis_actually_ran_real_pytest():
    rec = run_quality_suite()
    py = [r for r in rec.results if r.language == "python"]
    assert py and all(r.dynamic_ran for r in py)  # every Python task ran real pytest
    # the fully-covered Synapse harness passes essentially all hidden ground-truth tests
    syn = [r for r in rec.results if r.harness_id == "cortex_wrapped"]
    assert sum(r.functional_passed for r in syn) >= sum(r.functional_total for r in syn) - 1


def test_quality_report_renders(tmp_path):
    rec = run_quality_suite()
    out = tmp_path / "q.html"
    html = build_report(json.loads(rec.to_json()), out)  # dispatches to the Track Q builder
    assert out.exists()
    assert "Track Q" in html and "Synapse" in html and "c_cov" in html
