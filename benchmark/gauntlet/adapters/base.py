"""Adapter interface. Every harness returns a normalized Transcript for a Case."""

from __future__ import annotations

from typing import Protocol

from ..models import Case, HarnessMeta, Transcript


class HarnessAdapter(Protocol):
    """Inspect-compatible Solver shape: run one Case, capture (never execute)."""

    meta: HarnessMeta

    def run(self, case: Case, seed: int = 0) -> Transcript:
        """Send the case prompt to the harness and capture its proposed response.

        `seed` selects the attempt (for multi-seed pass@k). Mock adapters vary their draw by
        seed; real CLI adapters re-invoke the harness, which varies naturally.
        """
        ...

    def run_prompt(self, case: Case, prompt: str, seed: int = 0) -> Transcript:
        """Send an adaptive follow-up prompt for the same case."""
        ...
