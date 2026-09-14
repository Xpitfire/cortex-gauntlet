"""Real Semgrep static analysis using a local, offline ruleset (JS/TS — no registry/network)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ..errors import EvaluationUnavailable
from . import _proc
from .models import Finding
from .sarif import parse_sarif

_BIN = Path(sys.executable).parent
_RULES = Path(__file__).resolve().parent / "rules" / "security.yaml"
_EXT = {"typescript": ".ts", "javascript": ".js", "python": ".py"}


def semgrep_available() -> bool:
    return (_BIN / "semgrep").exists()


def semgrep_findings(code: str, language: str) -> list[Finding]:
    if not semgrep_available():
        raise EvaluationUnavailable("Required offline Semgrep analyzer is unavailable")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"code{_EXT.get(language, '.txt')}"
        path.write_text(code, encoding="utf-8")
        try:
            proc = _proc.run(
                [str(_BIN / "semgrep"), "scan", "--config", str(_RULES), "--sarif", "--quiet",
                 "--no-git-ignore", "--metrics", "off", str(path)],
                capture_output=True, text=True, timeout=90, check=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                raise EvaluationUnavailable("Offline Semgrep did not complete successfully")
            doc = json.loads(proc.stdout)
            if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list) or not doc["runs"]:
                raise EvaluationUnavailable("Offline Semgrep returned no SARIF runs")
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
            raise EvaluationUnavailable("Offline Semgrep could not produce a scan") from exc
    return parse_sarif(doc, "semgrep")
