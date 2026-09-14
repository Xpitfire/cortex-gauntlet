"""Shared real static + dynamic code analysis, reused by Track Q (audit) and Track G (functional).

Static: Bandit (security → CWE) + radon (complexity/LOC) + stdlib `ast` (structure), with graceful
degradation to `ast`-only when the tools are absent. Dynamic: runs the code's tests with pytest.
Real tools, not regex; Semgrep/njsscan (TS/JS) + Playwright are the next-step seams.
"""

from .deps import analyze_dependencies
from .dynamic import DynamicReport, run_node_tests_files, run_python_tests, run_python_tests_files
from .lint_types import LintTypeReport, lint_type_metrics
from .security import scan_repo, security_score
from .static import StaticReport, analyze_static
from .vertex import VertexScore, vertex_score

__all__ = [
    "DynamicReport", "LintTypeReport", "StaticReport", "VertexScore", "analyze_dependencies",
    "analyze_static", "lint_type_metrics", "run_node_tests_files", "run_python_tests",
    "run_python_tests_files", "scan_repo", "security_score", "vertex_score",
]
