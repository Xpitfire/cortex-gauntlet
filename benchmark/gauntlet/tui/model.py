"""Framework-agnostic view-model built from the event stream.

`ExperimentTree` is an `Observer`: feed it the same events the UI consumes and it maintains the
full tree state (groups, cells, statuses, captured prompt/output, counts, progress). The Textual
app renders from it; a headless test or console can inspect it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .events import (
    CellFinished,
    CellOutput,
    CellRef,
    CellStarted,
    CellStatus,
    Event,
    RunFinished,
    RunStarted,
)


@dataclass(slots=True)
class Cell:
    """One experiment cell (an item run against one harness) plus its captured I/O."""

    ref: CellRef
    harness_label: str
    status: CellStatus = CellStatus.PENDING
    prompt: str = ""
    output: str = ""  # streamed/terminal output (what the model produced)
    terminal_streams: dict[str, str] = field(default_factory=dict)
    terminal_labels: dict[str, str] = field(default_factory=dict)
    terminal_done: set[str] = field(default_factory=set)
    result: str = ""  # the final captured artifact (code/response), shown in the main view
    files: dict[str, str] = field(default_factory=dict)  # generated files (path → content) to browse
    detail: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    started_at: str = ""   # wall-clock HH:MM:SS the cell began
    finished_at: str = ""  # wall-clock HH:MM:SS the cell finished


@dataclass(slots=True)
class Group:
    """A named group of cells (e.g. a task/case/brief across harnesses)."""

    name: str
    cells: list[Cell] = field(default_factory=list)

    @property
    def status(self) -> CellStatus:
        """Roll-up: ERROR > FAIL > RUNNING > PENDING > PASS/SKIP (worst meaningful state wins)."""

        states = {cell.status for cell in self.cells}
        for status in (CellStatus.ERROR, CellStatus.FAIL, CellStatus.RUNNING, CellStatus.PENDING):
            if status in states:
                return status
        return CellStatus.PASS


class ExperimentTree:
    """Observer that accumulates run state into a browsable tree + progress counters."""

    def __init__(self) -> None:
        self.track: str = ""
        self.total: int = 0
        self.harnesses: list[tuple[str, str]] = []
        self.groups: list[Group] = []
        self.report_path: str | None = None
        self.finished: bool = False
        self._by_key: dict[str, Cell] = {}
        self._group_by_name: dict[str, Group] = {}

    # ---- counters -------------------------------------------------------
    def count(self, *statuses: CellStatus) -> int:
        return sum(1 for cell in self._by_key.values() if cell.status in statuses)

    @property
    def done(self) -> int:
        return self.count(CellStatus.PASS, CellStatus.FAIL, CellStatus.ERROR, CellStatus.SKIP)

    @property
    def progress(self) -> float:
        return self.done / self.total if self.total else 0.0

    def cell(self, key: str) -> Cell | None:
        return self._by_key.get(key)

    def preload(
        self, track: str, harnesses: list[tuple[str, str]], cells: list[tuple[CellRef, str]]
    ) -> None:
        """Seed the full plan up-front (all PENDING) so the tree shows everything before it runs."""

        self.track = track
        self.total = len(cells)
        self.harnesses = harnesses
        for ref, label in cells:
            self._ensure(ref, label)

    def load(self, track: str, harnesses: list[tuple[str, str]], cells: list[Cell]) -> None:
        """Populate the tree from already-scored cells (a saved run) — viewer mode, nothing runs."""

        self.track = track
        self.harnesses = harnesses
        self.total = len(cells)
        self.finished = True
        for cell in cells:
            self._by_key[cell.ref.key] = cell
            group = self._group_by_name.get(cell.ref.group)
            if group is None:
                group = Group(cell.ref.group)
                self._group_by_name[cell.ref.group] = group
                self.groups.append(group)
            group.cells.append(cell)

    # ---- event handling -------------------------------------------------
    def on_event(self, event: Event) -> None:
        if isinstance(event, RunStarted):
            self.track, self.total, self.harnesses = event.track, event.total, event.harnesses
        elif isinstance(event, CellStarted):
            cell = self._ensure(event.ref, event.harness_label)
            cell.prompt = event.prompt
            cell.status = CellStatus.RUNNING
            cell.started_at = datetime.now().strftime("%H:%M:%S")
        elif isinstance(event, CellOutput):
            cell = self._by_key.get(event.ref.key)
            if cell is not None:
                cell.output += event.chunk
                stream_id = event.stream_id or "terminal"
                cell.terminal_labels[stream_id] = event.stream_label or stream_id
                cell.terminal_streams[stream_id] = cell.terminal_streams.get(stream_id, "") + event.chunk
                if event.stream_done:
                    cell.terminal_done.add(stream_id)
        elif isinstance(event, CellFinished):
            cell = self._ensure(event.ref, "")
            cell.status = event.status
            cell.result = event.output
            cell.files = event.files
            cell.detail = event.detail
            cell.error = event.error
            cell.duration_ms = event.duration_ms
            cell.finished_at = datetime.now().strftime("%H:%M:%S")
        elif isinstance(event, RunFinished):
            self.finished = True
            self.report_path = event.report_path

    def _ensure(self, ref: CellRef, harness_label: str) -> Cell:
        cell = self._by_key.get(ref.key)
        if cell is None:
            group = self._group_by_name.get(ref.group)
            if group is None:
                group = Group(ref.group)
                self._group_by_name[ref.group] = group
                self.groups.append(group)
            cell = Cell(ref=ref, harness_label=harness_label or ref.harness_id)
            group.cells.append(cell)
            self._by_key[ref.key] = cell
        elif harness_label and cell.harness_label == cell.ref.harness_id:
            cell.harness_label = harness_label
        return cell
