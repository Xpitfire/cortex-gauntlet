"""Shared code-analysis data model (owned by analysis; re-exported by quality for compatibility)."""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import Severity


@dataclass(slots=True)
class Finding:
    cwe: str
    severity: Severity
    message: str
    line: int
    tool: str


@dataclass(slots=True)
class CodeMetrics:
    loc: int
    complexity: int
    functions: int
    duplication_pct: float
    comment_ratio: float
    has_tests: bool
    has_error_handling: bool
    # additive static-quality signals (ruff lint + mypy types) folded into the quality aspect; default
    # to clean so existing callers/results are unchanged until a track populates them (analysis.lint_types)
    lint_issues: int = 0
    type_errors: int = 0
    lint_score: float = 1.0
    type_score: float = 1.0
