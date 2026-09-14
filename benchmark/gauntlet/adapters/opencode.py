"""Adapter driving the open-source OpenCode CLI (sst/opencode) via `opencode run`.

OpenCode is an open-source, terminal-based coding agent — the OSS alternative in the
harness comparison. Requires an `opencode` binary on PATH. Used via `--adapters opencode`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .subprocess_base import SubprocessCliAdapter

# Pin a model opencode can actually serve from the user's OpenAI/Codex (ChatGPT-account) OAuth — the
# SAME gpt-5.5 + xhigh reasoning the codex arm uses, for a fair same-model comparison. opencode's own
# default is `gpt-5.5-pro`, which a ChatGPT account rejects ("not supported when using Codex with a
# ChatGPT account"), so the model AND the reasoning variant must be pinned explicitly.
OPENCODE_MODEL = "openai/gpt-5.5"
OPENCODE_VARIANT = "xhigh"  # provider reasoning effort (matches codex's model_reasoning_effort=xhigh)


class OpenCodeAdapter(SubprocessCliAdapter):
    binary_name = "opencode"

    def build_argv(self, binary: str, instruction: str, workspace: Path,
                   asset: Path | None = None) -> list[str]:
        # --dir pins the project dir to the isolated workspace; -m/--variant pin gpt-5.5 + xhigh (a model
        # the account serves). CRUCIALLY `--format json`: the DEFAULT mode renders an interactive ANSI UI
        # that expects a TTY — when piped it emits escapes to stderr and never completes (hangs to the
        # timeout). `json` is the non-interactive, parseable event stream.
        return [binary, "run", "--dir", str(workspace), "--dangerously-skip-permissions",
                "-m", OPENCODE_MODEL, "--variant", OPENCODE_VARIANT, "--format", "json", instruction]

    def _response_text(self, proc: subprocess.CompletedProcess[str]) -> str:
        """Extract the assistant text from opencode's `--format json` line-delimited events; fall back to
        the raw stdout (still scannable) if the schema doesn't match."""
        texts: list[str] = []

        def _harvest(node: object) -> None:
            if isinstance(node, dict):
                val = node.get("text")
                if isinstance(val, str) and val.strip():
                    texts.append(val)
                for v in node.values():
                    _harvest(v)
            elif isinstance(node, list):
                for v in node:
                    _harvest(v)

        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                _harvest(json.loads(line))
            except json.JSONDecodeError:
                continue
        return "\n".join(texts).strip() or (proc.stdout or "").strip() or (proc.stderr or "").strip()
