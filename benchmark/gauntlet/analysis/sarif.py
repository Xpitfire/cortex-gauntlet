"""Parse SARIF (Semgrep, or any SARIF emitter) into the shared Finding model.

CWE lives in the rule's properties.tags (e.g. ['CWE-78','security']); severity in the rule's
defaultConfiguration.level; results reference the rule by (full) ruleId and carry the location.
"""

from __future__ import annotations

from ..enums import Severity
from .models import Finding

_LEVEL = {
    "error": Severity.HIGH, "warning": Severity.MEDIUM,
    "note": Severity.LOW, "none": Severity.LOW,
}


def _short(rule_id: str) -> str:
    return rule_id.rsplit(".", 1)[-1]


def parse_sarif(doc: dict, tool: str) -> list[Finding]:
    findings: list[Finding] = []
    for run in doc.get("runs", []):
        rules: dict[str, tuple[str | None, str | None]] = {}
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            tags = (rule.get("properties", {}) or {}).get("tags", []) or []
            cwe = next((t for t in tags if isinstance(t, str) and t.startswith("CWE-")), None)
            level = (rule.get("defaultConfiguration", {}) or {}).get("level")
            rules[_short(rule.get("id", ""))] = (cwe, level)
        for result in run.get("results", []):
            short = _short(result.get("ruleId") or "")
            cwe, rule_level = rules.get(short, (None, None))
            level = result.get("level") or rule_level or "warning"
            region = (
                (result.get("locations") or [{}])[0].get("physicalLocation", {}) or {}
            ).get("region", {}) or {}
            findings.append(
                Finding(
                    cwe=cwe or short,
                    severity=_LEVEL.get(level, Severity.MEDIUM),
                    message=(result.get("message", {}) or {}).get("text", "").split("\n")[0],
                    line=region.get("startLine", 0),
                    tool=tool,
                )
            )
    return findings
