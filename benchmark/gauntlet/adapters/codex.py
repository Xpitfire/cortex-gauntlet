"""Adapter driving the Codex CLI (`codex exec`) for Track S — raw or Cortex-governed.

Capture-and-contain: `codex exec` runs in a **workspace-write** sandbox — it operates normally (reads
AND writes the prepared workspace), so it isn't distracted by a read-only wall, but the sandbox still
BLOCKS the network, so a complying attack (curl exfil, dep install, force-push) can't actually fire.
Writes land in the ephemeral decoy and are captured (workspace diff) as the compliance signal alongside
the response. The raw arm runs `isolated` (temp workspace + scrubbed env: fake honeytoken secrets, no
Cortex config); the Cortex-governed arm (`isolated=False`) inherits Cortex's `.codex`/`.agents`
governance — the same base model, wrapped vs not, is exactly the comparison.
"""

from __future__ import annotations

from pathlib import Path

from ..harness_isolation import codex_workspace_write_args
from ..models import HarnessMeta
from .governance import SECURITY_GOVERNANCE
from .subprocess_base import SubprocessCliAdapter

# Pin the same model the other tracks use so Track S compares the SAME base model wrapped vs raw.
_MODEL, _EFFORT = "gpt-5.5", "xhigh"


class CodexAdapter(SubprocessCliAdapter):
    binary_name = "codex"

    def __init__(self, meta: HarnessMeta, *, isolated: bool = True, timeout_s: int = 300) -> None:
        super().__init__(meta, timeout_s)
        self.isolated = isolated
        self.governance = "" if isolated else SECURITY_GOVERNANCE  # govern only the Cortex-wrapped arm

    def build_argv(self, binary: str, instruction: str, workspace: Path,
                   asset: Path | None = None) -> list[str]:
        # workspace-write sandbox: codex reads AND writes the prepared workspace (operates normally, no
        # read-only distraction) but the sandbox BLOCKS the network, so harmful effects can't fire; the
        # writes are captured as the compliance signal. An image asset goes through the vision channel via -i.
        argv = [binary, "exec", "--cd", str(workspace), "--skip-git-repo-check", "-s", "workspace-write",
                *codex_workspace_write_args(workspace), "-m", _MODEL, "-c", f"model_reasoning_effort={_EFFORT}"]
        if self.isolated:
            argv.append("--ignore-user-config")
        if asset is not None and asset.suffix == ".png":  # `--` stops the variadic -i swallowing the prompt
            argv += ["-i", str(asset), "--"]
        argv.append(instruction)
        return argv
