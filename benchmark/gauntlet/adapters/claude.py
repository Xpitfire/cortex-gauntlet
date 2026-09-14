"""Adapter driving the Claude Code CLI (`claude -p`) for Track S — raw or Cortex-governed.

Print mode with permission prompts bypassed so Claude has its normal tool surface; unsafe tool use is
the benchmark signal and is captured from stdout/stderr plus workspace writes. The raw arm runs
`isolated` (temp workspace + scrubbed env); the Cortex-governed arm (`isolated=False`) inherits Cortex's
`.claude`/`.agents` governance — the hooks/checks are part of what resists the jailbreak.
"""

from __future__ import annotations

from pathlib import Path

from ..models import HarnessMeta
from .governance import SECURITY_GOVERNANCE
from .subprocess_base import SubprocessCliAdapter

_MODEL = "opus"  # match the model the other tracks pin for Claude


class ClaudeAdapter(SubprocessCliAdapter):
    binary_name = "claude"

    def __init__(self, meta: HarnessMeta, *, isolated: bool = True, timeout_s: int = 300) -> None:
        super().__init__(meta, timeout_s)
        self.isolated = isolated
        self.governance = "" if isolated else SECURITY_GOVERNANCE  # govern only the Cortex-wrapped arm

    def build_argv(self, binary: str, instruction: str, workspace: Path,
                   asset: Path | None = None) -> list[str]:
        return [binary, "-p", instruction, "--dangerously-skip-permissions",
                "--add-dir", str(workspace), "--model", _MODEL]
