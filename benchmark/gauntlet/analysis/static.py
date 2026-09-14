"""Real static analysis for Python: Bandit (security→CWE) + radon (complexity) + ast (structure).

Bandit is a proper AST security analyzer (maps findings to CWE); radon gives real cyclomatic
complexity and raw LOC; the stdlib `ast` module supplies structure (functions, try/except, tests).
Falls back to ast-only metrics when bandit/radon are not installed.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..enums import Severity
from . import _proc
from ..errors import EvaluationUnavailable
from .models import CodeMetrics, Finding
from .semgrep_local import semgrep_findings

_BIN = Path(sys.executable).parent
_BANDIT_SEV = {"LOW": Severity.LOW, "MEDIUM": Severity.MEDIUM, "HIGH": Severity.HIGH}


@dataclass(slots=True)
class StaticReport:
    findings: list[Finding]
    metrics: CodeMetrics
    parsed: bool  # did the code parse (syntactically valid)


def _toolcmd(name: str) -> list[str]:
    binary = _BIN / name
    return [str(binary)] if binary.exists() else [sys.executable, "-m", name]


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> str:
    try:
        proc = _proc.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
    except (subprocess.SubprocessError, OSError) as exc:
        raise EvaluationUnavailable("Required static analyzer could not run") from exc
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        raise EvaluationUnavailable("Required static analyzer did not produce a result")
    return proc.stdout


def _bandit(path: Path) -> list[Finding]:
    # -s B101: assert-used is expected in self-tests and is not a real vulnerability here.
    raw = _run(_toolcmd("bandit") + ["-s", "B101", "-f", "json", "-q", str(path)])
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict) or not isinstance(doc.get("results"), list):
            raise EvaluationUnavailable("Bandit returned an invalid result")
        results = doc["results"]
    except json.JSONDecodeError as exc:
        raise EvaluationUnavailable("Bandit returned invalid JSON") from exc
    findings: list[Finding] = []
    for r in results:
        cwe_id = (r.get("issue_cwe") or {}).get("id")
        findings.append(
            Finding(
                cwe=f"CWE-{cwe_id}" if cwe_id else r.get("test_id", "?"),
                severity=_BANDIT_SEV.get(r.get("issue_severity", "LOW"), Severity.LOW),
                message=r.get("issue_text", "").split("\n")[0],
                line=r.get("line_number", 0),
                tool="bandit",
            )
        )
    return findings


def _radon_complexity(path: Path) -> int:
    raw = _run(_toolcmd("radon") + ["cc", "-j", str(path)])
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return 0
    return sum(b.get("complexity", 0) for blocks in data.values() if isinstance(blocks, list) for b in blocks)


def _radon_raw(path: Path) -> tuple[int, int]:
    raw = _run(_toolcmd("radon") + ["raw", "-j", str(path)])
    try:
        entry = next(iter(json.loads(raw or "{}").values()), {})
    except json.JSONDecodeError:
        entry = {}
    return entry.get("sloc", 0), entry.get("comments", 0)


def _duplication(code: str) -> float:
    nontrivial = [ln.strip() for ln in code.splitlines() if len(ln.strip()) > 12]
    return (len(nontrivial) - len(set(nontrivial))) / len(nontrivial) if nontrivial else 0.0


_JS_COMPLEXITY = re.compile(r"\b(if|for|while|case|catch)\b|&&|\|\|")
_JS_FUNC = re.compile(r"\bfunction\b|=>|\bdef ")


def analyze_static(code: str, language: str = "python") -> StaticReport:
    """Dispatch to the right real analyzer: Bandit/radon/ast for Python, Semgrep for JS/TS."""

    if language in ("typescript", "javascript"):
        return _analyze_js(code, language)
    return _analyze_python(code)


def _analyze_js(code: str, language: str) -> StaticReport:
    findings = semgrep_findings(code, language)  # real Semgrep, local offline ruleset
    lines = [ln for ln in code.splitlines() if ln.strip()]
    nontrivial = [ln.strip() for ln in lines if len(ln.strip()) > 12]
    duplication = (len(nontrivial) - len(set(nontrivial))) / len(nontrivial) if nontrivial else 0.0
    metrics = CodeMetrics(
        loc=len(lines),
        complexity=sum(len(_JS_COMPLEXITY.findall(ln)) for ln in lines),
        functions=len(_JS_FUNC.findall(code)),
        duplication_pct=round(duplication, 4),
        comment_ratio=0.0,
        has_tests=bool(re.search(r"\b(describe|it|test)\(", code)),
        has_error_handling=bool(re.search(r"\btry\b|\bcatch\b", code)),
    )
    return StaticReport(findings=findings, metrics=metrics, parsed=True)


def _analyze_python(code: str) -> StaticReport:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "module.py"
        path.write_text(code, encoding="utf-8")
        findings = _bandit(path)
        complexity = _radon_complexity(path)
        sloc, comments = _radon_raw(path)

    try:
        tree = ast.parse(code)
        parsed = True
        functions = sum(isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) for n in ast.walk(tree))
        has_error_handling = any(isinstance(n, ast.Try) for n in ast.walk(tree))
        has_tests = any(
            isinstance(n, ast.FunctionDef) and n.name.startswith("test_") for n in ast.walk(tree)
        )
    except SyntaxError:
        parsed, functions, has_error_handling, has_tests = False, 0, False, False

    sloc = sloc or len([ln for ln in code.splitlines() if ln.strip()])
    metrics = CodeMetrics(
        loc=sloc, complexity=complexity, functions=functions,
        duplication_pct=round(_duplication(code), 4),
        comment_ratio=round(comments / sloc, 4) if sloc else 0.0,
        has_tests=has_tests, has_error_handling=has_error_handling,
    )
    return StaticReport(findings=findings, metrics=metrics, parsed=parsed)
