"""Real CLI code-gen adapters (codex / claude / cortex+Synapse / omp / opencode).

Best-effort, non-interactive invocations that write a workspace; untested against a live,
authenticated CLI here (live runs need auth + tokens). The cortex adapter governs the agent
(Synapse-wrapped) via the Cortex runtime, which writes in the runtime rather than the local
workspace — so it captures the code from the agent's final reply instead of the cwd.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from ..harness_isolation import codex_workspace_write_args
from ..models import HarnessMeta
from ..resilience import is_rate_limited, rate_limit_retry
from .base import SubprocessCodeGen, _extract_code
from .models import CodeGenRequest, CodeGenResult

# Real model id + reasoning each live CLI should pin, so a sweep is reproducible regardless of the
# tool's local default config. Mirrors the display labels in run.py PRESETS. opencode has no
# openai/anthropic credentials here (only opencode-hosted models), so it runs its configured default.
# The Cortex arm wraps the SAME base CLI as its raw counterpart (codex→gpt-5.5, claude→opus) and pins
# the identical model — the only difference is the Synapse loop (score_task), a clean same-model A/B.
LIVE_MODELS: dict[str, dict[str, str]] = {
    "codex": {"model": "gpt-5.5", "effort": "xhigh"},
    "claude": {"model": "opus"},  # latest Opus (4.8); --model alias
    # gpt-5.5 + xhigh via the user's OpenAI/Codex OAuth (same as codex). MUST pin a model the account
    # serves — opencode's default gpt-5.5-pro is rejected by a ChatGPT account; preflight verifies it.
    "opencode": {"model": "openai/gpt-5.5", "variant": "xhigh"},
    "omp": {"model": os.environ.get("GAUNTLET_OMP_MODEL", "openai-codex/gpt-5.5")},
}

# a per-file section in a multi-file echo: `FILE: path` then (after optional blank lines) a fenced
# block with that file's contents. The `\s*` before the fence tolerates the blank line agents emit
# between the `FILE:` label and the code fence (otherwise only the first file is captured).
_FILEBLOCK = re.compile(r"FILE:\s*(\S+)[^\n]*\n\s*```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)

# `cortex agent ask` prints task status lines (`<id> running/queued/succeeded/failed`) before the body
_STATUS_LINE = re.compile(r"^\S+ (?:queued|running|succeeded|failed)$")


def _parse_files(reply: str) -> dict[str, str]:
    return {path.strip(): body.strip() + "\n" for path, body in _FILEBLOCK.findall(reply)}


def _cortex_reply(stdout: str) -> tuple[str, str]:
    """(reply_text, error) from `cortex agent ask` stdout: leading status lines, then either the
    task-log JSON envelope {status, result.payloads[].text} on success, or an error line on a failed
    task (e.g. a runtime auth/provider failure). Surfaces the failure reason instead of swallowing it."""
    start = stdout.find("{")
    if start < 0:  # no envelope -> the task failed; the last non-status line carries the reason
        tail = [s for ln in stdout.splitlines() if (s := ln.strip()) and not _STATUS_LINE.match(s)]
        return "", (tail[-1] if tail else "agent task produced no reply")
    try:
        data, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except json.JSONDecodeError:
        return "", "could not parse agent reply"
    if data.get("status") not in (None, "ok", "succeeded"):
        return "", str(data.get("summary") or data.get("status") or "agent task did not succeed")
    payloads = (data.get("result") or {}).get("payloads") or []
    return "\n".join(p.get("text", "") for p in payloads), ""


class CodexCodeGen(SubprocessCodeGen):
    binary_name = "codex"

    def __init__(self, meta: HarnessMeta, timeout_s: int = 300, model: str = "", effort: str = "") -> None:
        super().__init__(meta, timeout_s)
        self.model, self.effort = model, effort

    def build_argv(self, binary: str, prompt: str, workspace: Path, main_file: str) -> list[str]:
        # --json exposes command_execution events the TUI can map to terminal tabs. workspace-write stays
        # enabled, with explicit add-dir roots for copied managed scaffold dirs such as `.agents/tasks`.
        argv = [binary, "exec", "--json", "--cd", str(workspace), "--skip-git-repo-check",
                "--ignore-user-config", "-s", "workspace-write", *codex_workspace_write_args(workspace)]
        if self.model:
            argv += ["-m", self.model]
        if self.effort:
            argv += ["-c", f"model_reasoning_effort={self.effort}"]
        argv.append(prompt)
        return argv

    def stdout_text(self, stdout: str) -> str:
        texts: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {}) if isinstance(event, dict) else {}
            if item.get("type") == "agent_message" and item.get("text"):
                texts.append(item["text"])
        return "\n".join(texts) or stdout


class ClaudeCodeGen(SubprocessCodeGen):
    binary_name = "claude"

    def __init__(self, meta: HarnessMeta, timeout_s: int = 300, model: str = "") -> None:
        super().__init__(meta, timeout_s)
        self.model = model

    def build_argv(self, binary: str, prompt: str, workspace: Path, main_file: str) -> list[str]:
        # print (non-interactive) mode; skip permission prompts so it can write files (cwd=workspace)
        argv = [binary, "-p", prompt, "--dangerously-skip-permissions", "--add-dir", str(workspace)]
        if self.model:
            argv += ["--model", self.model]
        return argv


class OpenCodeCodeGen(SubprocessCodeGen):
    binary_name = "opencode"

    def __init__(self, meta: HarnessMeta, timeout_s: int = 300, model: str = "", variant: str = "") -> None:
        super().__init__(meta, timeout_s)
        self.model, self.variant = model, variant

    def build_argv(self, binary: str, prompt: str, workspace: Path, main_file: str) -> list[str]:
        # --dir pins the project dir to the sandbox (opencode ignores process cwd); skip permission prompts;
        # --format json keeps it non-interactive (the default ANSI UI hangs when piped — it writes files
        # either way, which is what codegen captures)
        argv = [binary, "run", "--dir", str(workspace), "--dangerously-skip-permissions", "--format", "json"]
        if self.model:
            argv += ["-m", self.model]
        if self.variant:
            argv += ["--variant", self.variant]
        argv.append(prompt)
        return argv


class OmpCodeGen(SubprocessCodeGen):
    binary_name = "omp"

    def __init__(self, meta: HarnessMeta, timeout_s: int = 300, model: str = "") -> None:
        super().__init__(meta, timeout_s)
        self.model = model

    def build_argv(self, binary: str, prompt: str, workspace: Path, main_file: str) -> list[str]:
        argv = [binary, "-p", "--cwd", str(workspace), "--approval-mode", "yolo"]
        if self.model:
            argv += ["--model", self.model]
        argv.append(prompt)
        return argv


class CortexCodeGen(SubprocessCodeGen):
    binary_name = "cortex"

    def __init__(self, meta: HarnessMeta, provider: str = "codex", timeout_s: int = 600) -> None:
        super().__init__(meta, timeout_s)
        self.provider = provider

    def build_argv(self, binary: str, prompt: str, workspace: Path, main_file: str) -> list[str]:
        # `agent ask` runs the governed (Synapse) agent and prints its final reply. The runtime agent
        # would otherwise write files in the runtime (not locally), so force it to echo every file inline
        # in a path-labelled format (works for single- and multi-file solutions alike).
        # No --model: the runtime policy governs the model (overrides are rejected for the main agent).
        prompt = (
            f"{prompt}\n\nDo NOT create, write, or edit any files on disk. Instead respond with the "
            "complete contents of every file the solution needs: for each file output a line "
            "'FILE: <relative/path>' immediately followed by a fenced code block with that file's contents."
        )
        return [binary, "agent", "ask", "--provider", self.provider, "--timeout", str(self.timeout_s),
                "--", prompt]

    def generate(self, request: CodeGenRequest) -> CodeGenResult:
        # the agent writes files in the runtime, not locally, so capture the code from its reply text
        binary = shutil.which(self.binary_name)
        if binary is None:
            return CodeGenResult(self.meta.id, "", error="cortex CLI not found on PATH")
        argv = self.build_argv(binary, request.prompt, Path.cwd(), request.main_file)

        def run_once():
            env = {**os.environ, "CORTEX_CODE_APPROVAL": "deny"}
            return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  timeout=request.timeout_s or self.timeout_s, env=env, check=False)

        start = time.monotonic()
        try:  # the governed task can hit a provider rate limit too; back off before giving up
            proc, limited = rate_limit_retry(
                run_once, lambda p: is_rate_limited((p.stdout or "") + (p.stderr or "")))
        except (subprocess.SubprocessError, OSError) as exc:
            return CodeGenResult(self.meta.id, "", error=str(exc))
        wall_ms = int((time.monotonic() - start) * 1000)
        reply, reply_error = _cortex_reply(proc.stdout or "")
        files = _parse_files(reply)  # path-labelled multi-file echo
        if not files:  # fall back to a single unlabelled code block
            code = _extract_code(reply) or reply.strip()
            files = {request.main_file: code} if code.strip() else {}
        main_code = files.get(request.main_file) or "\n\n".join(files.values())
        ok = bool(files)
        if not ok and limited:  # persistent rate limit, no reply — flag it (pause/resume, not a failure)
            return CodeGenResult(self.meta.id, "", wall_ms=wall_ms, rate_limited=True,
                                 error="rate limited: " + ((reply_error or proc.stdout or "")[:200]))
        return CodeGenResult(
            backend=self.meta.id, main_code=main_code, files=files,
            tokens=len((proc.stdout or "").split()), wall_ms=wall_ms, ok=ok,
            error="" if ok else (reply_error or proc.stderr or "no code in agent reply")[:300],
        )


def _base_adapter(base: str, meta: HarnessMeta):
    """The local base-CLI adapter for codex / omp / claude (the proper, OAuth-authed tools on the host)."""
    cfg = LIVE_MODELS.get(base, {})
    if base == "claude":
        return ClaudeCodeGen(meta, model=cfg.get("model", ""))
    if base == "omp":
        return OmpCodeGen(meta, model=cfg.get("model", ""))
    return CodexCodeGen(meta, model=cfg.get("model", ""), effort=cfg.get("effort", ""))


# provider spec -> code-gen adapter
def build_codegen(provider: str, meta: HarnessMeta):
    kind, _, sub = provider.partition(":")
    if kind in ("cortex", "cortex-review"):
        # Governed arm: wrap the SAME local base CLI as the raw arm (codex / Claude Code). score_task
        # drives it through the real Synapse plan→validate→repair loop (harness.uses_synapse). No remote
        # runtime, no separate auth — it uses the proper local tool the user already authenticated.
        # `cortex-review` adds the M5 read-only review inner-loop (harness.uses_review) on the same base.
        return _base_adapter(sub or "codex", meta)
    if kind == "cortex-runtime":
        # Opt-in: dispatch to the governed Cortex *runtime* instead (needs the runtime's provider auth,
        # e.g. an OpenAI API key for gpt-5.5 via the Responses API). Kept for when that is configured.
        return CortexCodeGen(meta, provider=sub or "codex")
    cfg = LIVE_MODELS.get(provider) or LIVE_MODELS.get(kind, {})
    if kind == "codex":
        return CodexCodeGen(meta, model=cfg.get("model", ""), effort=cfg.get("effort", ""))
    if kind == "claude":
        return ClaudeCodeGen(meta, model=cfg.get("model", ""))
    if kind == "opencode":
        return OpenCodeCodeGen(meta, model=cfg.get("model", ""), variant=cfg.get("variant", ""))
    if kind == "omp":
        return OmpCodeGen(meta, model=cfg.get("model", ""))
    raise ValueError(f"unknown live provider: {provider!r}")


# which harness preset a live provider maps to (for labelling/comparison)
PROVIDER_HARNESS = {
    "codex": "codex_cli_raw",
    "claude": "claude_code",
    "opencode": "opencode",
    "omp": "omp",
    "cortex": "cortex_wrapped",
    "cortex:omp": "cortex_omp",
    "cortex:claude": "cortex_claude",
    "cortex-review": "cortex_reviewed",
    "cortex-review:claude": "cortex_claude_reviewed",
    "cortex-runtime": "cortex_wrapped",
    "cortex-runtime:claude": "cortex_claude",
}


def provider_harness_id(provider: str) -> str:
    # exact spec first (cortex:claude → cortex_claude), else the base (cortex / cortex:codex → cortex_wrapped)
    return PROVIDER_HARNESS.get(provider) or PROVIDER_HARNESS.get(
        provider.partition(":")[0], "codex_cli_raw"
    )
