"""Real static (Bandit/radon/ast) + dynamic (pytest) analysis — runs the actual tools."""

from gauntlet.analysis import analyze_static, run_python_tests

VULN = (
    "import os, hashlib\n"
    "def run(cmd):\n"
    "    os.system('echo ' + cmd)\n"  # CWE-78 (Bandit B605)
    "def digest(p):\n"
    "    return hashlib.md5(p).hexdigest()\n"  # CWE-327 (Bandit B303)
)
CLEAN = (
    "import subprocess\n"
    "def run(cmd):\n"
    "    try:\n"
    "        subprocess.run([cmd], shell=False, check=True)\n"
    "    except subprocess.CalledProcessError:\n"
    "        return None\n"
)


def test_bandit_flags_real_vulnerabilities():
    report = analyze_static(VULN)
    assert report.parsed
    cwes = {f.cwe for f in report.findings}
    assert any(c.startswith("CWE-") for c in cwes)  # Bandit produced real CWE findings
    assert report.metrics.functions == 2


def test_clean_code_has_no_high_severity_findings():
    report = analyze_static(CLEAN)
    assert report.parsed and report.metrics.has_error_handling
    assert all(f.severity.value != "high" for f in report.findings)


def test_unparseable_code_is_flagged():
    assert analyze_static("def broken(:\n  pass").parsed is False


def test_dynamic_pytest_runs_and_counts_pass_fail():
    module = "def add(a, b):\n    return a + b\n"
    passing = "from solution import add\n\ndef test_ok():\n    assert add(2, 3) == 5\n"
    failing = "from solution import add\n\ndef test_bad():\n    assert add(2, 3) == 6\n"
    ok = run_python_tests(module, passing)
    bad = run_python_tests(module, failing)
    assert ok.ran and ok.passed == 1 and ok.failed == 0
    assert bad.ran and bad.failed == 1 and bad.pass_rate == 0.0
