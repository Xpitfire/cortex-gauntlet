"""Typed event stream + bus — the contract between an experiment runner and any observer.

Events flow one way: a runner emits, observers (the view-model, the Textual app, a console
logger) react. Nothing here imports a UI framework, so the same stream drives a TUI, a plain
console, a log file, or a future web view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

# status glyph + colour per cell state (vivid hex, tuned for a true-black background)
_GLYPH = {
    "pending": "•", "running": "▶", "pass": "✓", "fail": "✗", "error": "⚠", "skip": "–",
}
_COLOR = {
    "pending": "#565f89", "running": "#7dcfff", "pass": "#9ece6a", "fail": "#f7768e",
    "error": "#ff9e64", "skip": "#565f89",
}


class CellStatus(str, Enum):
    """Lifecycle state of one experiment cell."""

    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # the cell raised — isolated, never aborts the run
    SKIP = "skip"

    @property
    def glyph(self) -> str:
        return _GLYPH[self.value]

    @property
    def color(self) -> str:
        return _COLOR[self.value]

    @property
    def terminal(self) -> bool:
        return self not in (CellStatus.PENDING, CellStatus.RUNNING)


@dataclass(frozen=True, slots=True)
class CellRef:
    """Stable address of a cell within the experiment tree: track → group → item × harness."""

    track: str
    group: str
    name: str
    harness_id: str

    @property
    def key(self) -> str:
        return f"{self.track}/{self.group}/{self.name}/{self.harness_id}"


@dataclass(slots=True)
class RunStarted:
    track: str
    total: int
    harnesses: list[tuple[str, str]]  # (id, label)


@dataclass(slots=True)
class CellStarted:
    ref: CellRef
    harness_label: str
    prompt: str


@dataclass(slots=True)
class CellOutput:
    """A chunk of live output (e.g. streamed CLI stdout) for the cell's terminal preview."""

    ref: CellRef
    chunk: str
    stream_id: str = "terminal"
    stream_label: str = "terminal"
    stream_done: bool = False


@dataclass(slots=True)
class CellFinished:
    ref: CellRef
    status: CellStatus
    output: str
    detail: dict[str, str] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)  # generated artifacts (path → content) to browse
    error: str | None = None  # traceback when status is ERROR
    duration_ms: int = 0


@dataclass(slots=True)
class RunFinished:
    passed: int
    failed: int
    errored: int
    skipped: int
    report_path: str | None = None
    paused: bool = False  # stopped early on a persistent rate limit; resume from the checkpoint
    pause_reason: str = ""


Event = RunStarted | CellStarted | CellOutput | CellFinished | RunFinished


@runtime_checkable
class Observer(Protocol):
    """Anything that reacts to the event stream."""

    def on_event(self, event: Event) -> None: ...


class EventBus:
    """Fan-out of events to subscribed observers (synchronous, in emit order)."""

    def __init__(self) -> None:
        self._observers: list[Observer] = []

    def subscribe(self, observer: Observer) -> None:
        self._observers.append(observer)

    def emit(self, event: Event) -> None:
        for observer in self._observers:
            observer.on_event(event)
