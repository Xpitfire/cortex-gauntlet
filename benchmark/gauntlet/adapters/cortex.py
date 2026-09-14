"""Real adapter driving a harness through the Cortex CLI (`cortex agent ask`).

Requires an authenticated `cortex` CLI on PATH. Used via `--adapters cortex:<provider>`.
"""

from __future__ import annotations

from pathlib import Path

from ..models import HarnessMeta
from .subprocess_base import SubprocessCliAdapter


class CortexAdapter(SubprocessCliAdapter):
    binary_name = "cortex"
    isolated = False  # the Cortex arm is governed by the Cortex runtime — that is exactly what is tested

    def __init__(self, meta: HarnessMeta, provider: str = "auto", timeout_s: int = 180) -> None:
        super().__init__(meta, timeout_s)
        self.provider = provider

    # the cortex runtime is agentic: it operates on the prepared workspace and the prompt points it at
    # the rendered asset file (its provider's vision/file tools determine how far it gets).
    def build_argv(self, binary: str, instruction: str, workspace: Path,
                   asset: Path | None = None) -> list[str]:
        return [binary, "agent", "ask", "--provider", self.provider, "--", instruction]
