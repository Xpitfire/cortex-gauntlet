"""A non-TUI observer: print progress to stdout.

Used when there is no TTY (CI, piped output) or `--no-tui`. Proves the event core is reusable
beyond Textual — the same stream that drives the IDE drives a plain progress log here.
"""

from __future__ import annotations

from .events import (
    CellFinished,
    CellStarted,
    CellStatus,
    Event,
    RunFinished,
    RunStarted,
)


class ConsoleObserver:
    """Emit one line per cell completion plus a final summary."""

    def __init__(self) -> None:
        self._total = 0
        self._done = 0

    def on_event(self, event: Event) -> None:
        if isinstance(event, RunStarted):
            self._total = event.total
            harnesses = ", ".join(label for _, label in event.harnesses)
            print(f"▶ {event.track}: {event.total} cells across {harnesses}")
        elif isinstance(event, CellStarted):
            print(f"  · {event.ref.group} / {event.ref.name} [{event.harness_label}] …", flush=True)
        elif isinstance(event, CellFinished):
            self._done += 1
            mark = event.status.glyph
            tail = ""
            if event.status is CellStatus.ERROR and event.error:
                tail = "  " + event.error.strip().splitlines()[-1]
            elif event.detail:
                tail = "  " + " · ".join(f"{k}={v}" for k, v in event.detail.items())
            pct = self._done / self._total * 100 if self._total else 100.0
            print(f"  {mark} [{pct:5.1f}%] {event.ref.name} [{event.ref.harness_id}]{tail}", flush=True)
        elif isinstance(event, RunFinished):
            print(f"\n✓ {event.passed} pass · ✗ {event.failed} fail · "
                  f"⚠ {event.errored} error · – {event.skipped} skip")
            if event.report_path:
                print(f"  run: {event.report_path}")
