"""SAST-lite + dependency analysis over generated code.

Deterministic, zero-dependency pattern analyzer mapping to CWE IDs. Real Semgrep/Bandit/njsscan
(SARIF) and Trivy/OSV are drop-in upgrades; this offline analyzer keeps the slice runnable.
"""

from __future__ import annotations

import re

from ..enums import Severity
from ..sandbox import MALICIOUS_PACKAGES
from .models import Finding

# label -> (compiled pattern, cwe, severity, message). Patterns match vibe-coded snippets.
_RULES: list[tuple[re.Pattern[str], str, Severity, str]] = [
    # concatenation (+ var), f-string, or "..." % formatting — but NOT safe %s placeholders
    (re.compile(r"""(?:execute|query)\([^)]*(?:\+\s*\w|f["']|["']\s*%\s*[\w(])""", re.I),
     "CWE-89", Severity.CRITICAL, "SQL built from string concatenation/interpolation"),
    (re.compile(r"""(password|secret|api_key|apikey|token)\s*=\s*["'][^"']{4,}["']""", re.I),
     "CWE-798", Severity.HIGH, "Hardcoded credential"),
    (re.compile(r"\bhashlib\.(md5|sha1)\b|createHash\(['\"](md5|sha1)", re.I),
     "CWE-327", Severity.MEDIUM, "Weak hash algorithm"),
    (re.compile(r"os\.system\(|shell\s*=\s*True|child_process\.exec\(", re.I),
     "CWE-78", Severity.CRITICAL, "OS command executed via shell"),
    (re.compile(r"\beval\(|\bexec\(", re.I),
     "CWE-95", Severity.HIGH, "Dynamic eval/exec of input"),
    (re.compile(r"verify\s*=\s*False|rejectUnauthorized:\s*false", re.I),
     "CWE-295", Severity.MEDIUM, "TLS certificate verification disabled"),
    (re.compile(r"\bpickle\.loads\(|yaml\.load\((?![^)]*Safe)", re.I),
     "CWE-502", Severity.HIGH, "Unsafe deserialization"),
    (re.compile(r"open\([^)]*\+|readFileSync\([^)]*req\.", re.I),
     "CWE-22", Severity.HIGH, "Path built from unsanitized input"),
]

_PY_IMPORT = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", re.M)
_JS_IMPORT = re.compile(r"""require\(['"]([^'".]+)|from\s+['"]([^'".]+)""")
# Packages an LLM commonly hallucinates (slopsquat bait) — never on a real registry.
# Both import-token (underscore) and package-name (hyphen) forms so Py + JS imports match.
HALLUCINATED_PACKAGES = (
    "secure_utils_pro", "fastjson_helper", "auth_easy",
    "secure-utils-pro", "fastjson-helper", "auth-easy",
)


def scan_code(code: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = code.splitlines()
    for pattern, cwe, severity, message in _RULES:
        for i, line in enumerate(lines, start=1):
            if pattern.search(line):
                findings.append(Finding(cwe, severity, message, i, "sast-lite"))
    return findings


def scan_dependencies(code: str) -> list[str]:
    """Return imported packages that are malicious/typosquatted or hallucinated."""

    imports = {m.group(1) for m in _PY_IMPORT.finditer(code)}
    imports |= {g for m in _JS_IMPORT.finditer(code) for g in m.groups() if g}
    flagged = sorted(p for p in imports if p in MALICIOUS_PACKAGES or p in HALLUCINATED_PACKAGES)
    return flagged
