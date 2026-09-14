"""Adapter driving the OMP CLI via ``omp -p``."""

from __future__ import annotations

import os
from pathlib import Path

from .subprocess_base import SubprocessCliAdapter
from .governance import SECURITY_GOVERNANCE

OMP_MODEL = os.environ.get("GAUNTLET_OMP_MODEL", "openai-codex/gpt-5.5")


class OmpAdapter(SubprocessCliAdapter):
    binary_name = "omp"

    def __init__(self, meta, timeout_s: int = 300, *, isolated: bool = True) -> None:
        super().__init__(meta, timeout_s)
        self.isolated = isolated
        self.governance = "" if isolated else SECURITY_GOVERNANCE

    def build_argv(self, binary: str, instruction: str, workspace: Path, asset: Path | None = None) -> list[str]:
        return [
            binary,
            "-p",
            "--cwd",
            str(workspace),
            "--model",
            OMP_MODEL,
            "--approval-mode",
            "yolo",
            instruction,
        ]
