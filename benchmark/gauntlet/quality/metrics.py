"""Code-quality metrics (complexity, duplication, tests, error handling) — stdlib only.

Drop-in upgrades: radon/lizard (complexity), jscpd (duplication), SonarQube (maintainability).
"""

from __future__ import annotations

import re

from .models import CodeMetrics

_COMMENT = re.compile(r"^\s*(#|//|/\*|\*)")
_COMPLEXITY = re.compile(r"\b(if|elif|for|while|case|catch|except)\b|&&|\|\||\band\b|\bor\b")
_FUNC = re.compile(r"^\s*(?:async\s+)?(?:def |function |const \w+\s*=\s*\()", re.M)
_TEST = re.compile(r"\bdef test_|\bit\(|\bdescribe\(|\.test\(", re.I)
_ERR = re.compile(r"\btry\b|\bcatch\b|\bexcept\b")


def analyze(code: str) -> CodeMetrics:
    lines = [ln for ln in code.splitlines() if ln.strip()]
    comments = [ln for ln in lines if _COMMENT.match(ln)]
    code_only = [ln for ln in lines if not _COMMENT.match(ln)]
    nontrivial = [ln.strip() for ln in code_only if len(ln.strip()) > 12]
    duplication = (len(nontrivial) - len(set(nontrivial))) / len(nontrivial) if nontrivial else 0.0
    return CodeMetrics(
        loc=len(code_only),
        complexity=sum(len(_COMPLEXITY.findall(ln)) for ln in code_only),
        functions=len(_FUNC.findall(code)),
        duplication_pct=round(duplication, 4),
        comment_ratio=round(len(comments) / len(lines), 4) if lines else 0.0,
        has_tests=bool(_TEST.search(code)),
        has_error_handling=bool(_ERR.search(code)),
    )


def check_breakdown(result) -> dict[str, dict[str, float]]:
    """Per-category check tally for one (task, harness) result, so 6/7 functional tests with clean
    lint/types is NOT misrepresented as a total failure. Returns {category: {passed, total}} including
    only the categories that actually ran:
      - functionality: hidden functional tests (real pytest) — passed/total tests
      - quality:       lint + types (ruff/mypy for Python, eslint/tsc for JS/TS)
      - security:      static-analysis findings — one check: clean (1) or has findings (0)
    """

    out: dict[str, dict[str, float]] = {}
    if result.dynamic_ran and result.functional_total:
        out["functionality"] = {"passed": float(result.functional_passed),
                                 "total": float(result.functional_total)}
    if result.language in {"python", "javascript", "typescript", "js", "ts"}:
        m = result.metrics
        out["quality"] = {"passed": round(m.lint_score + m.type_score, 3), "total": 2.0}
    out["security"] = {"passed": 0.0 if result.findings else 1.0, "total": 1.0}
    return out


def smell_count(metrics: CodeMetrics) -> int:
    """Maintainability smells (each adds to per-KLOC technical debt)."""

    smells = 0
    if not metrics.has_tests:
        smells += 1
    if not metrics.has_error_handling:
        smells += 1
    if metrics.duplication_pct > 0.10:
        smells += 1
    if metrics.functions and metrics.complexity / metrics.functions > 6:
        smells += 1  # high cognitive complexity per function
    if metrics.comment_ratio < 0.05:
        smells += 1
    return smells
