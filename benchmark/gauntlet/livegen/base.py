"""CodeGenAdapter protocol + a subprocess base that drives a CLI and captures written files."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from ..errors import HarnessSetupError, HarnessTimeout
from ..harness_isolation import raw_harness_env
from ..models import HarnessMeta
from ..resilience import is_rate_limited, rate_limit_retry
from .models import CodeGenRequest, CodeGenResult
from .streaming import run_streamed

_GLOB = {"python": "*.py", "typescript": "*.ts", "javascript": "*.js"}

# Prepended to a governed arm's prompt once the Cortex scaffold is in the workspace: the scaffold is a
# GENERIC managed environment, so the harness's FIRST job is to adapt it to this project, THEN build —
# exactly the "adapt the template to the project requirements" first phase a real Cortex setup runs.
_SCAFFOLD_NOTE = (
    "This workspace is ALREADY a Cortex project scaffold — a managed environment with `.agents/` "
    "instructions + verification hooks + quality gates and the tool adapters. Work in two ordered "
    "phases:\n"
    "PHASE 0 — ADAPT the scaffold to THIS project FIRST: read `.agents/instructions.md`, `CLAUDE.md` "
    "and `AGENTS.md`; set the project's identity, prune or replace any scaffold parts that do not fit "
    "the required stack/runtime, and tailor the instructions and quality gates to the task. The "
    "scaffold is a generic starting point, not the deliverable.\n"
    "PHASE 1 — BUILD the requested application on top of the adapted scaffold, honouring the hooks and "
    "gates and studying `.agents/examples/` for the expected structure. Keep the `.agents/` governance "
    "in place; do not delete it.\n\n"
)
# matches a fenced code block ```lang\n...\n``` (optional language tag) in a CLI's stdout
_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)

# Track-P repo capture: a full-stack repo is polyglot (json/html/css/svg/md/lockfiles + ts), so a
# single-language glob drops package.json/index.html/manifest/tests. Walk the whole tree instead,
# excluding installed deps, VCS, caches, and build output (the sandbox reinstalls + rebuilds anyway).
_REPO_SKIP_DIRS = frozenset({
    "node_modules", ".git", ".hg", "dist", "build", ".next", ".nuxt", ".svelte-kit",
    ".cache", ".turbo", ".parcel-cache", "coverage", ".pnpm-store", ".venv", "venv",
    "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache", ".gauntlet-raw-home",
})
_REPO_MAX_BYTES = 512 * 1024  # skip oversized/binary blobs; source files are far smaller


def _extract_code(text: str) -> str:
    blocks = _FENCE.findall(text)
    return (max(blocks, key=len).strip() + "\n") if blocks else ""


def _capture_repo(workspace: Path) -> dict[str, str]:
    """Capture the whole generated repo tree as text, minus deps/VCS/caches/build output."""
    files: dict[str, str] = {}
    for path in workspace.rglob("*"):
        if not path.is_file() or _REPO_SKIP_DIRS.intersection(path.parts):
            continue
        try:
            if path.stat().st_size > _REPO_MAX_BYTES:
                continue
            files[str(path.relative_to(workspace))] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # unreadable or binary — not source, skip it
            continue
    return files


def _capture_glob(workspace: Path, language: str) -> dict[str, str]:
    """Capture single-language source files (keyed by workspace-relative path), skipping caches."""
    return {
        str(p.relative_to(workspace)): p.read_text(errors="replace")
        for p in workspace.rglob(_GLOB.get(language, "*"))
        if p.is_file() and "__pycache__" not in p.parts and ".ruff_cache" not in p.parts
    }


class CodeGenAdapter(Protocol):
    meta: HarnessMeta

    def generate(self, request: CodeGenRequest) -> CodeGenResult: ...


class SubprocessCodeGen:
    """Run a real coding-agent CLI in a temp workspace, then capture the files it wrote."""

    binary_name: str = ""

    def __init__(self, meta: HarnessMeta, timeout_s: int = 300) -> None:
        self.meta = meta
        self.timeout_s = timeout_s

    def build_argv(self, binary: str, prompt: str, workspace: Path, main_file: str) -> list[str]:
        raise NotImplementedError

    def stdout_text(self, stdout: str) -> str:
        return stdout

    def _seed_scaffold(self, workspace: Path, reporter, *, governance_only: bool = False) -> None:
        """Governed arm only: materialize the Cortex project template (instructions, hooks, checks,
        scripts, adapters) into `workspace` so the harness runs INSIDE the scaffold — the actual
        wrapping under test. `governance_only` lays just the managed core (no full service stack) for
        non-full-stack tasks. Fail-fast: if the template is missing or extracts nothing, RAISE rather
        than let the arm run as a plain harness and report a raw result under a 'Cortex' label."""

        from ..bootstrap import bootstrap_template, template_available

        if not template_available():
            raise HarnessSetupError(
                f"governed arm '{self.meta.id}' requires the Cortex project template "
                "(.template-cache/project-template.tar.gz) but it is missing — refusing to run as a plain harness")
        written = bootstrap_template(workspace, governance_only=governance_only)
        if written <= 0:
            raise HarnessSetupError(
                f"governed arm '{self.meta.id}': the Cortex template extracted no files — base setup "
                "is broken, refusing to continue as a plain harness")
        if reporter is not None:
            scope = "governance core" if governance_only else "full template"
            reporter.note(f"⊞ Cortex scaffold materialized ({written} files, {scope}: .agents/ "
                          "instructions+hooks, .cortex/, quality gates, adapters) — adapt, then build on top")

    def generate(self, request: CodeGenRequest) -> CodeGenResult:
        binary = shutil.which(self.binary_name)
        if binary is None:
            return CodeGenResult(self.meta.id, "", error=f"{self.binary_name} CLI not found on PATH")
        reporter = request.reporter
        mirror = Path(request.mirror_dir) if request.mirror_dir else None
        with TemporaryDirectory() as tmp:  # outside the repo: raw harness can't discover Cortex config
            workspace = Path(tmp)
            prompt = request.prompt
            if request.scaffold:  # governed arm: lay the Cortex scaffold first, then adapt + build on it
                self._seed_scaffold(workspace, reporter,
                                    governance_only=request.scaffold_governance_only)
                prompt = _SCAFFOLD_NOTE + prompt
            argv = self.build_argv(binary, prompt, workspace, request.main_file)

            def run_once():
                # raw_harness_env() gives raw arms sterile tool homes, so user-global skills/MCP/session
                # state cannot leak in. stdin closed so a CLI can't hang
                # on an interactive prompt. The inactivity watchdog kills only a SILENT (hung) process —
                # a long, actively-working build (new output or new files) keeps running, streaming live.
                return run_streamed(
                    argv, cwd=workspace, env=raw_harness_env(workspace), watch_dir=workspace, mirror_dir=mirror,
                    inactivity_s=request.inactivity_s, ceiling_s=request.ceiling_s,
                    on_output=(reporter.cli_line if reporter is not None else None),
                    on_files=(reporter.files_seen if reporter is not None else None),
                    on_tick=(reporter.tick if reporter is not None else None),
                )

            start = time.monotonic()
            try:  # retry with bounded backoff on a rate limit before giving up — never silent-fail it
                proc, limited = rate_limit_retry(
                    run_once, lambda p: is_rate_limited((p.stderr or "") + (p.stdout or "")))
            except (subprocess.SubprocessError, OSError) as exc:
                return CodeGenResult(self.meta.id, "", error=str(exc))
            wall_ms = int((time.monotonic() - start) * 1000)
            # capture whatever the CLI wrote — even when it hung, so the loop can salvage/retry, never
            # lose an hour of partial work (the old fixed-timeout path discarded it on TimeoutExpired)
            files = (_capture_repo(workspace) if request.capture_repo
                     else _capture_glob(workspace, request.language))
            if proc.stuck or proc.exceeded:
                reason = (f"no output or file activity for {request.inactivity_s}s — terminated as stuck"
                          if proc.stuck else f"exceeded the {request.ceiling_s}s safety ceiling")
                msg = f"{self.binary_name} {reason}"
                if reporter is not None:
                    reporter.note(f"⏱ {msg}")
                if not files:  # produced nothing at all -> a timeout SKIP (excluded from %), as before
                    raise HarnessTimeout(msg)
                main = files.get(request.main_file) or "\n\n".join(files.values())
                return CodeGenResult(self.meta.id, main, files=files, wall_ms=wall_ms,
                                     ok=bool(main.strip()), timed_out=True, error=msg)
        main_code = files.get(request.main_file) or "\n\n".join(files.values())
        stdout_text = self.stdout_text(proc.stdout or "")
        if not main_code.strip():  # CLI printed code instead of writing a file → recover it from stdout
            recovered = _extract_code(stdout_text)
            if recovered.strip():
                main_code, files = recovered, {request.main_file: recovered}
        ok = bool(main_code.strip())
        if not ok and limited:  # persistent rate limit, no code — flag it (pause/resume, not a failure)
            return CodeGenResult(self.meta.id, "", wall_ms=wall_ms, rate_limited=True,
                                 error="rate limited: " + ((proc.stderr or proc.stdout or "")[:200]))
        return CodeGenResult(
            backend=self.meta.id, main_code=main_code, files=files,
            tokens=len(stdout_text.split()), wall_ms=wall_ms, ok=ok,
            # include stdout in the failure reason — an auth/login error is printed there, not stderr,
            # so the caller's auth-pause can see it instead of a generic "no file produced"
            error="" if ok else ((proc.stderr or "").strip() or stdout_text.strip()
                                 or "no file produced")[:300],
        )
