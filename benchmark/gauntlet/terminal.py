"""Structured terminal chunks for live experiment observers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerminalChunk:
    chunk: str
    stream_id: str = "terminal"
    stream_label: str = "terminal"
    stream_done: bool = False
