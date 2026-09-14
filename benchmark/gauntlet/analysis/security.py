"""Repo-wide security scan → a severity-weighted [0,1] signal (the famous-OSS-SAST scoring axis).

Scans the whole generated repository with Semgrep — the de-facto open-source SAST for code
vulnerabilities — when the `semgrep` CLI is available (its security-audit + secrets rulesets), and
otherwise falls back to the bundled offline Semgrep ruleset + Bandit via `analyze_static`. Either way
findings carry a CWE + severity; `security_score` maps them to [0,1] (1.0 = clean). One scan pass is
shared with code-health to avoid re-running analyzers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..enums import Severity
from . import _proc
from .models import Finding
from .static import analyze_static
from .sarif import parse_sarif

_SEV_WEIGHT = {Severity.CRITICAL: 1.0, Severity.HIGH: 0.6, Severity.MEDIUM: 0.3, Severity.LOW: 0.1}


def _lang_of(path: str) -> str | None:
    if path.endswith(".py"):
        return "python"
    if path.endswith((".ts", ".tsx")):
        return "typescript"
    if path.endswith((".js", ".jsx")):
        return "javascript"
    return None


def _semgrep_repo(files: dict[str, str]) -> list[Finding] | None:
    """Full Semgrep scan of the repo (security-audit + secrets) when the CLI is installed, else None."""

    if shutil.which("semgrep") is None:
        return None
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, content in files.items():
            p = (root / rel).resolve()
            if p != root and not p.is_relative_to(root):
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        argv = ["semgrep", "--config", "p/security-audit", "--config", "p/secrets",
                "--sarif", "--quiet", "--timeout", "120", str(root)]
        try:
            proc = _proc.run(argv, capture_output=True, text=True, timeout=240, check=False)
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            doc = json.loads(proc.stdout)
            if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list) or not doc["runs"]:
                return None
            return parse_sarif(doc, "semgrep")
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            return None


def scan_repo(files: dict[str, str]) -> tuple[list[Finding], str]:
    """Return (findings, tool). Prefer the Semgrep CLI; fall back to offline Semgrep ruleset + Bandit."""

    full = _semgrep_repo(files)
    if full is not None:
        return full, "semgrep (security-audit + secrets)"
    by_lang: dict[str, list[str]] = {}  # batch per language to bound subprocess cost
    for path, content in files.items():
        lang = _lang_of(path)
        if lang:
            by_lang.setdefault(lang, []).append(content)
    findings = [f for lang, blocks in by_lang.items()
                for f in analyze_static("\n\n".join(blocks), lang).findings]
    return findings, "semgrep-local + bandit (offline fallback)"


def security_score(findings: list[Finding]) -> float:
    """Severity-weighted → [0,1] (1.0 = no findings). Saturates as weighted findings accumulate."""

    penalty = sum(_SEV_WEIGHT.get(f.severity, 0.2) for f in findings)
    return max(0.0, 1.0 - min(1.0, penalty * 0.2))
