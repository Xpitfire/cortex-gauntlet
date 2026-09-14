"""Execute generated modules against hidden tests inside the sealed Docker evaluator.

Both language paths mount an immutable generated tree into a non-root, deny-egress, resource-bounded
container. Unavailable confinement fails loud; it is benchmark infrastructure, never a candidate zero.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import SandboxUnavailable
from . import _proc

# Pytest's terminal summary: an integer followed by passed, failed, or error.
_SUMMARY = re.compile(r"(\d+) (passed|failed|error)")
# Node's TAP reporter summary lines: `# tests N`, `# pass N`, `# fail N`.
_TAP = re.compile(r"^# (tests|pass|fail) (\d+)", re.MULTILINE)
_NODE_EXT = {"typescript": "ts", "javascript": "js"}


@dataclass(slots=True)
class DynamicReport:
    ran: bool
    passed: int
    failed: int
    errors: int
    output: str

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _write_tree(workspace: Path, files: dict[str, str]) -> list[str]:
    """Materialize generated text without allowing absolute or parent-traversal paths."""

    root = workspace.resolve()
    rejected = []
    for rel, content in files.items():
        if Path(rel).is_absolute():
            rejected.append(rel)
            continue
        path = (root / rel).resolve()
        if path == root or not path.is_relative_to(root):
            rejected.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return rejected


def run_sandboxed(
    files: dict[str, str], extra_files: dict[str, str], command: list[str], timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run a trusted evaluator command over untrusted files in the content-addressed sandbox image."""

    from ..project.sandbox import BASE_TAG, _ensure_base, docker_available

    if not docker_available():
        raise SandboxUnavailable("Docker is unavailable; refusing to execute generated code on the host")
    base_ok, base_error = _proc.retry_fd_race(_ensure_base)
    if not base_ok:
        raise SandboxUnavailable(f"sandbox evaluator image failed to build: {base_error}")
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        workspace.chmod(0o755)
        rejected = _write_tree(workspace, {**files, **extra_files})
        if rejected:
            raise ValueError(f"rejected unsafe generated paths: {rejected[:10]}")
        argv = [
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--user", "0:0", "--cap-drop", "ALL",
            "--cap-add", "NET_ADMIN", "--cap-add", "SETUID", "--cap-add", "SETGID",
            "--security-opt", "no-new-privileges", "--cpus", "1",
            "--memory", "512m", "--memory-swap", "512m", "--pids-limit", "64",
            "--ulimit", "nofile=256:256", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "-e", "HOME=/tmp", "-e", "TMPDIR=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{workspace}:/work:ro", "-w", "/work", BASE_TAG,
            "python3", "/probe/network_guard.py", "--",
            "timeout", "--signal=KILL", f"{timeout}s", *command,
        ]
        try:
            proc = _proc.run(
                argv, capture_output=True, text=True, timeout=timeout + 30, check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise SandboxUnavailable(f"sandbox evaluator failed to run: {type(exc).__name__}") from exc
    if proc.returncode in (125, 126, 127):
        reason = (proc.stderr or proc.stdout or "docker evaluator failed")[-400:]
        raise SandboxUnavailable(reason)
    return proc


def run_python_tests(module_code: str, test_code: str, timeout: int = 30) -> DynamicReport:
    """Single-module convenience: write solution.py + tests and run pytest."""

    return run_python_tests_files({"solution.py": module_code}, test_code, timeout)


def run_python_tests_files(files: dict[str, str], test_code: str, timeout: int = 30) -> DynamicReport:
    """Run pytest against an immutable generated Python tree in the sealed evaluator."""

    try:
        proc = run_sandboxed(
            files,
            {"test_solution.py": test_code},
            ["python3", "-m", "pytest", "-q", "--no-header", "--tb=short",
             "-p", "no:cacheprovider", "--", "test_solution.py"],
            timeout,
        )
    except ValueError as exc:
        return DynamicReport(ran=True, passed=0, failed=0, errors=1, output=str(exc))
    if proc.returncode == 124:
        return DynamicReport(ran=True, passed=0, failed=0, errors=1, output="sandbox test timeout")

    output = (proc.stdout or "") + (proc.stderr or "")
    counts = {"passed": 0, "failed": 0, "error": 0}
    for match in _SUMMARY.finditer(output):
        counts[match.group(2)] = int(match.group(1))
    return DynamicReport(
        ran=True, passed=counts["passed"], failed=counts["failed"],
        errors=counts["error"], output=output[-2000:],
    )


def run_node_tests_files(
    files: dict[str, str], test_code: str, language: str, timeout: int = 60
) -> DynamicReport:
    """Run Node's TAP test runner against an immutable generated JS/TS tree in the sealed evaluator."""

    ext = _NODE_EXT.get(language)
    if ext is None or not test_code.strip():
        return DynamicReport(ran=False, passed=0, failed=0, errors=0, output="")
    testfile = f"solution.test.{ext}"
    try:
        proc = run_sandboxed(
            files,
            {testfile: test_code},
            ["node", "--test", "--test-reporter=tap", "--", testfile],
            timeout,
        )
    except ValueError as exc:
        return DynamicReport(ran=True, passed=0, failed=0, errors=1, output=str(exc))
    if proc.returncode == 124:
        return DynamicReport(ran=True, passed=0, failed=0, errors=1, output="sandbox test timeout")

    output = (proc.stdout or "") + (proc.stderr or "")
    counts = {"tests": 0, "pass": 0, "fail": 0}
    for match in _TAP.finditer(output):
        counts[match.group(1)] = int(match.group(2))
    ran = "# tests" in output or counts["tests"] > 0
    return DynamicReport(
        ran=ran, passed=counts["pass"], failed=counts["fail"], errors=0, output=output[-2000:],
    )
