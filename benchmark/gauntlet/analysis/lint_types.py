"""Additive static-quality metrics: ruff (lint) + mypy (type-check) over a generated file tree.

These are SUPPLEMENTARY signals folded into the *quality aspect* of a track's score (generative /
Repo / Project). They run fast over already-written files — lint + type-check only, never execution,
never more code generation. A clean tree scores 1.0. Unsupported file types report ran=False.
Missing or failed required analyzers raise EvaluationUnavailable: no evidence is not a clean score.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import EvaluationUnavailable
from . import _proc

# benchmark/ root — where the reproducible node toolchain (package.json + node_modules + eslint config)
# lives, mirroring how ruff/mypy live in the Python .venv
_BENCH_DIR = Path(__file__).resolve().parents[2]
_ESLINT_CONFIG = _BENCH_DIR / "eslint.config.mjs"
# eslint v9's flat-config base path is the config file's directory, so the tree it lints must live UNDER
# benchmark/ (a /tmp tree is "outside base path" and silently ignored) — use a dedicated ignored dir
_LINT_WS = _BENCH_DIR / ".lint-tmp"
_WEB_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_TS_EXT = (".ts", ".tsx")
# tsc diagnostics that are environment noise (deps not installed in the isolated scoring tree), not real
# type defects — the JS/TS analogue of mypy's --ignore-missing-imports
_TS_NOISE = ("TS2307", "TS2305", "TS7016", "TS2792", "TS6133", "TS2580", "TS2584")
_TS_ERR = re.compile(r"\berror (TS\d+):")  # matches a tsc diagnostic line and captures its code

# A real (not just-syntax) lint set: pycodestyle errors/warnings + pyflakes + bugbear + simplify +
# pyupgrade. E501 (line length) is excluded — it is noisy and a weak quality signal that would
# otherwise dominate the density. This is broader than the Synapse repair gate (E9,F only) on purpose:
# the gate decides "is it runnable", this metric grades "is it clean".
_RUFF_SELECT = "E,F,W,B,SIM,UP"
_RUFF_IGNORE = "E501"

# mypy error codes that are annotation pedantry, not real type defects — counting them would penalise
# every quick solution that omits annotations and swamp the genuine signal (undefined names, bad calls,
# arg/return-type mismatches), so they are excluded from the type-error count.
_MYPY_NOISE_CODES = ("[no-untyped-def]", "[annotation-unchecked]", "[var-annotated]")

_ISSUES_PER_100_LOC_AT_ZERO = {"lint": 40.0, "type": 25.0}  # density that drives a dimension to 0.0
_LOC_FLOOR = 40  # treat tiny files as at least this many LOC so one issue can't zero the score
_TIMEOUT_S = 90


@dataclass(slots=True)
class LintTypeReport:
    lint_issues: int
    type_errors: int
    lint_score: float  # [0,1] cleanliness — 1.0 = lint-clean
    type_score: float  # [0,1] cleanliness — 1.0 = type-clean
    ran: bool          # False for unsupported languages → caller ignores it


def _density_score(issues: int, loc: int, kind: str) -> float:
    """1.0 when clean; decays linearly with issues-per-100-LOC, floored at 0."""

    if issues <= 0:
        return 1.0
    per_100 = issues / max(loc, _LOC_FLOOR) * 100
    return round(max(0.0, 1.0 - per_100 / _ISSUES_PER_100_LOC_AT_ZERO[kind]), 3)


def _write_tree(workspace: Path, files: dict[str, str]) -> int:
    # `files` is UNTRUSTED model output — REFUSE any key that escapes `workspace` (an absolute or `../`
    # key would write arbitrary HOST files via a naive join; CWE-22 path traversal). Skip unsafe keys.
    base = workspace.resolve()
    loc = 0
    for rel, content in files.items():
        if Path(rel).is_absolute():
            continue
        path = (base / rel).resolve()
        if path != base and not path.is_relative_to(base):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        loc += sum(1 for ln in content.splitlines() if ln.strip())
    return loc


def _ruff_issue_count(workspace: Path) -> int | None:
    try:
        proc = _proc.run(
            [sys.executable, "-m", "ruff", "check", "--select", _RUFF_SELECT, "--ignore", _RUFF_IGNORE,
             "--output-format", "json", str(workspace)],
            capture_output=True, text=True, timeout=_TIMEOUT_S, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        return None
    try:
        results = json.loads(proc.stdout)
        return len(results) if isinstance(results, list) else None
    except json.JSONDecodeError:
        return None


def _mypy_error_count(workspace: Path) -> int | None:
    try:
        # cwd=workspace so the repo's strict config never leaks in; count only genuine type errors
        proc = _proc.run(
            # --check-untyped-defs: type-check bodies of UNannotated functions too (generated code is
            # often unannotated) so real defects — undefined names, bad calls — are caught, while we still
            # exclude the missing-annotation nags below; cwd=workspace so the repo's strict config can't leak
            [sys.executable, "-m", "mypy", "--ignore-missing-imports", "--follow-imports=silent",
             "--check-untyped-defs", "--no-error-summary", "--cache-dir=/dev/null", "."],
            cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode not in (0, 1, 2) or "usage: mypy" in (proc.stderr or ""):
        return None
    errors = [line for line in (proc.stdout or "").splitlines() if ": error:" in line]
    # Availability uses raw diagnostics; annotation-only findings can legitimately
    # yield zero scored defects after applying the existing noise policy.
    if proc.returncode and not errors:
        return None
    return sum(not any(code in line for code in _MYPY_NOISE_CODES) for line in errors)


def _resolve_node_tool(name: str) -> list[str] | None:
    """Prefer the benchmark's pinned toolchain (`benchmark/node_modules/.bin`), then a global install."""

    local = _BENCH_DIR / "node_modules" / ".bin" / name
    if local.exists():
        return [str(local)]
    found = shutil.which(name)
    return [found] if found else None


def _tsc_type_errors(workspace: Path, ts_files: list[str]) -> int | None:
    """Genuine TS type-error count (module-resolution noise filtered), or None if tsc is unavailable."""

    tool = _resolve_node_tool("tsc")
    if tool is None or not ts_files:
        return None
    try:
        # explicit files bypass any repo tsconfig; --skipLibCheck avoids @types noise; deps are NOT
        # installed in the isolated tree, so module-resolution diagnostics (TS2307…) are filtered as noise
        proc = _proc.run([*tool, "--noEmit", "--allowJs", "--checkJs", "--jsx", "react-jsx", "--skipLibCheck", *ts_files],
                         cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)
    except (subprocess.SubprocessError, OSError):
        return None
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode not in (0, 1, 2) or (proc.returncode and not _TS_ERR.search(out)):
        return None
    return sum(1 for ln in out.splitlines()
               if (m := _TS_ERR.search(ln)) and m.group(1) not in _TS_NOISE)


def _eslint_lint_issues(workspace: Path, web_files: list[str]) -> int | None:
    """ESLint problem count via the benchmark's pinned flat config, or None if eslint is unavailable."""

    tool = _resolve_node_tool("eslint")
    if tool is None or not web_files or not _ESLINT_CONFIG.exists():
        return None
    try:
        proc = _proc.run([*tool, "--config", str(_ESLINT_CONFIG), "-f", "json", *web_files],
                         cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        return None
    try:
        results = json.loads(proc.stdout)
        if not isinstance(results, list) or not results:
            return None
    except json.JSONDecodeError:
        return None
    return sum(r.get("errorCount", 0) + r.get("warningCount", 0) for r in results)


def _report(lint_issues: int | None, type_errors: int | None, loc: int) -> LintTypeReport:
    """Only successfully measured dimensions can receive cleanliness credit."""

    missing = [name for name, count in (("lint", lint_issues), ("types", type_errors)) if count is None]
    if missing:
        raise EvaluationUnavailable("Required analyzers unavailable: " + ", ".join(missing))
    return LintTypeReport(
        lint_issues, type_errors, _density_score(lint_issues, loc, "lint"),
        _density_score(type_errors, loc, "type"), True,
    )


def _python_stack(py: dict[str, str]) -> LintTypeReport:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        loc = _write_tree(ws, py)
        return _report(_ruff_issue_count(ws), _mypy_error_count(ws), loc)


def _web_stack(web: dict[str, str]) -> LintTypeReport:
    _LINT_WS.mkdir(exist_ok=True)  # eslint base-path requirement: the tree must live under benchmark/
    with tempfile.TemporaryDirectory(dir=_LINT_WS) as tmp:
        ws = Path(tmp)
        loc = _write_tree(ws, web)
        present = [r for r in web if (ws / r).exists()]  # _write_tree skips path-traversal keys
        ts_files = [str(ws / r) for r in present]
        web_files = [str(ws / r) for r in present]
        return _report(_eslint_lint_issues(ws, web_files), _tsc_type_errors(ws, ts_files), loc)


def lint_type_metrics(files: dict[str, str], language: str = "python") -> LintTypeReport:
    """Additive lint + type cleanliness over a generated tree: ruff+mypy for Python, eslint+tsc for
    JS/TS. `language` selects the stack (`python` | `javascript` | `typescript`); `auto` scores every
    stack present and averages. Missing required tools raise EvaluationUnavailable."""

    lang = language.lower()
    py = {p: c for p, c in files.items() if p.endswith(".py")}
    web = {p: c for p, c in files.items() if p.endswith(_WEB_EXT)}
    if lang == "python":
        web = {}
    elif lang in ("javascript", "js", "typescript", "ts"):
        py = {}
    reports = [r for r in (_python_stack(py) if py else None, _web_stack(web) if web else None)
               if r is not None and r.ran]
    if not reports:
        return LintTypeReport(0, 0, 1.0, 1.0, ran=False)
    n = len(reports)
    return LintTypeReport(
        lint_issues=sum(r.lint_issues for r in reports),
        type_errors=sum(r.type_errors for r in reports),
        lint_score=round(sum(r.lint_score for r in reports) / n, 3),
        type_score=round(sum(r.type_score for r in reports) / n, 3),
        ran=True,
    )
