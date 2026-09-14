"""Phase 2: real Semgrep (TS/JS) static analysis + SARIF normalization + dependency gate."""

from gauntlet.analysis import analyze_dependencies, analyze_static
from gauntlet.analysis.deps import pypi_exists
from gauntlet.analysis.sarif import parse_sarif
from gauntlet.analysis.semgrep_local import semgrep_available, semgrep_findings

VULN_TS = (
    "import * as fs from 'fs';\n"
    "import * as child_process from 'child_process';\n"
    "function h(req: any) {\n"
    "  child_process.exec('convert ' + req.query.f);\n"  # CWE-78
    "  const n = eval(req.query.e);\n"  # CWE-95
    "  return fs.readFileSync(req.query.f);\n"  # CWE-22
    "}\n"
)


def test_semgrep_finds_real_ts_vulnerabilities():
    if not semgrep_available():  # tool guard (installed in this env)
        return
    cwes = {f.cwe for f in semgrep_findings(VULN_TS, "typescript")}
    assert {"CWE-78", "CWE-95", "CWE-22"} <= cwes
    assert all(f.tool == "semgrep" for f in semgrep_findings(VULN_TS, "typescript"))


def test_analyze_static_dispatches_to_semgrep_for_typescript():
    report = analyze_static(VULN_TS, "typescript")
    assert report.parsed and report.metrics.functions >= 1
    if semgrep_available():
        assert any(f.cwe.startswith("CWE-") for f in report.findings)


def test_clean_ts_has_no_findings():
    if not semgrep_available():
        return
    clean = "function add(a: number, b: number): number {\n  return a + b;\n}\n"
    assert semgrep_findings(clean, "typescript") == []


def test_sarif_parser_maps_rule_cwe_and_severity():
    doc = {"runs": [{
        "tool": {"driver": {"rules": [
            {"id": "x.y.rule1", "properties": {"tags": ["CWE-89", "security"]},
             "defaultConfiguration": {"level": "error"}},
        ]}},
        "results": [{"ruleId": "x.y.rule1", "message": {"text": "sql"},
                     "locations": [{"physicalLocation": {"region": {"startLine": 7}}}]}],
    }]}
    findings = parse_sarif(doc, "semgrep")
    assert len(findings) == 1
    assert findings[0].cwe == "CWE-89" and findings[0].severity.value == "high"
    assert findings[0].line == 7 and findings[0].tool == "semgrep"


def test_dependency_gate_flags_malicious_and_ignores_stdlib():
    assert analyze_dependencies("import os, json, hashlib\n", "python", check_registry=False) == []
    flagged = analyze_dependencies("import gauntlet_malware_helper\n", "python", check_registry=False)
    assert "gauntlet_malware_helper" in flagged


def test_registry_existence_gate_when_online():
    # Online: a real package exists, a hallucinated one does not. Offline: returns None -> skip.
    real = pypi_exists("requests")
    fake = pypi_exists("definitely-not-a-real-pkg-zzz999-gauntlet")
    if real is None or fake is None:
        return  # offline; gate degrades gracefully
    assert real is True and fake is False
