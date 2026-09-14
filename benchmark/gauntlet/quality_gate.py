"""Per-iteration import, lint, and self-test gate over a generated workspace.

Python runs a static stdlib/local import check, Ruff, and the agent's own pytest tests. TypeScript and
JavaScript run the agent's own tests through Node. Every executable step uses the sealed, non-root,
deny-egress Docker evaluator; these are never the hidden acceptance tests.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass

from .analysis.dynamic import run_sandboxed

_TAP_COUNT = re.compile(r"^# (tests|pass|fail) (\d+)$", re.M)  # node --test TAP summary lines
_TS_EXT = {"typescript": ("ts", "tsx"), "javascript": ("js", "jsx", "mjs", "cjs")}
# the agent's OWN test files (never the hidden acceptance tests)

_EVALUATOR_MODULES = frozenset({"pytest"})
_TEST_FILE = re.compile(r"(\.(test|spec)\.[mc]?[jt]sx?$)|(^|/)__tests__/", re.I)


@dataclass(slots=True)
class GateResult:
    passed: bool
    ruff_ok: bool
    tests_ok: bool
    has_tests: bool
    summary: str
    imports_ok: bool = True


def _local_modules(files: dict[str, str]) -> set[str]:
    """Top-level module/package names the tree itself provides (file stems + package dirs)."""

    names: set[str] = set()
    for rel in files:
        parts = rel.split("/")
        names.add(parts[0].removesuffix(".py"))  # top-level file or package dir
        if rel.endswith(".py"):
            names.add(parts[-1].removesuffix(".py"))  # the module's own stem (any depth)
    return names


def _unresolved_imports(files: dict[str, str]) -> list[str]:
    """Top-level absolute imports not provided by the generated tree or the Python standard library."""

    local = _local_modules(files)
    unresolved: set[str] = set()
    for rel, content in files.items():
        if not rel.endswith(".py"):
            continue
        test_file = rel.rsplit("/", 1)[-1].startswith("test_") or "/tests/" in f"/{rel}"
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue  # ruff reports syntax separately; don't double-count it as an import failure
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            else:
                continue  # relative imports resolve within the tree
            for mod in mods:
                if (
                    mod not in local
                    and mod not in sys.stdlib_module_names
                    and not (test_file and mod in _EVALUATOR_MODULES)
                ):
                    unresolved.add(mod)
    return sorted(unresolved)


def run_quality_gate(files: dict[str, str], timeout: int = 90, language: str = "python") -> GateResult:
    """Self-verify the generated tree; gate strategy follows the task language."""

    if language in _TS_EXT:
        return _run_node_gate(files, language, timeout)
    return _run_python_gate(files, timeout)


def _run_node_gate(files: dict[str, str], language: str, timeout: int) -> GateResult:
    """TS/JS gate: run the agent's own tests in the sealed evaluator."""

    test_files = [rel for rel in files if rel.endswith(_dot_exts(language)) and _TEST_FILE.search(rel)]
    if not test_files:
        return GateResult(False, ruff_ok=True, tests_ok=False, has_tests=False, summary="self_tests=MISSING")
    try:
        proc = run_sandboxed(
            files, {}, ["node", "--test", "--test-reporter=tap", "--", *test_files], timeout,
        )
    except ValueError as exc:
        return GateResult(False, ruff_ok=True, tests_ok=False, has_tests=True, summary=str(exc))
    output = (proc.stdout or "") + (proc.stderr or "")
    counts = {match.group(1): int(match.group(2)) for match in _TAP_COUNT.finditer(output)}
    ran = "# tests" in output or counts.get("tests", 0) > 0
    tests_ok = ran and counts.get("pass", 0) > 0 and counts.get("fail", 0) == 0
    summary = f"node_tests={'ok' if tests_ok else 'FAIL'} (pass={counts.get('pass', 0)} fail={counts.get('fail', 0)})"
    if not tests_ok:
        summary += "\n" + output[-400:]
    return GateResult(passed=tests_ok, ruff_ok=True, tests_ok=tests_ok, has_tests=True, summary=summary)


def _dot_exts(language: str) -> tuple[str, ...]:
    return tuple(f".{e}" for e in _TS_EXT[language])


def _run_python_gate(files: dict[str, str], timeout: int = 90) -> GateResult:
    """Run ruff + the agent's own pytest in the sealed evaluator."""

    unresolved = _unresolved_imports(files)
    imports_ok = not unresolved
    try:
        ruff = run_sandboxed(
            files, {},
            ["ruff", "check", "--select", "E9,F", "--ignore", "F401,F841", "--quiet", "/work"],
            timeout,
        )
    except ValueError as exc:
        return GateResult(False, False, False, False, str(exc), imports_ok)
    ruff_ok = ruff.returncode == 0
    test_files = [rel for rel in files if rel.endswith(".py") and rel.rsplit("/", 1)[-1].startswith("test_")]
    has_tests = bool(test_files)
    tests_ok, test_out = True, ""
    if has_tests:
        try:
            pytest = run_sandboxed(
                files, {},
                ["python3", "-m", "pytest", "-q", "--no-header", "--tb=short",
                 "-p", "no:cacheprovider", "--", *test_files],
                timeout,
            )
        except ValueError as exc:
            return GateResult(False, ruff_ok, False, True, str(exc), imports_ok)
        tests_ok = pytest.returncode == 0
        test_out = (pytest.stdout or pytest.stderr or "")[-600:]

    passed = imports_ok and ruff_ok and tests_ok and has_tests
    parts = [
        f"imports={'ok' if imports_ok else 'FAIL'}",
        f"ruff={'ok' if ruff_ok else 'FAIL'}",
        f"self_tests={'ok' if tests_ok else 'FAIL'}" if has_tests else "self_tests=MISSING",
    ]
    summary = " · ".join(parts)
    if not imports_ok:
        summary += "\nunresolved imports (not stdlib/local): " + ", ".join(unresolved)
    if not ruff_ok:
        summary += "\n" + (ruff.stdout or ruff.stderr or "")[-400:]
    if has_tests and not tests_ok:
        summary += "\n" + test_out
    return GateResult(passed=passed, ruff_ok=ruff_ok, tests_ok=tests_ok, has_tests=has_tests,
                      summary=summary, imports_ok=imports_ok)
