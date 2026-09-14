"""A self-narrating progress reporter for long live builds — the Synapse loop's "mini-harness" voice.

A live Track-P/Track-G build can run for hours. Without continuous feedback a user can't tell a healthy
long build from a hang. This wraps an `emit(text)` sink (the TUI cell stream, or stdout for `gauntlet
run`) so the build continuously narrates what it is doing: the plan, each pass's requirement deltas,
files as they are written, the raw agent output as it streams, and a heartbeat when it goes quiet — and
mirrors the same events as structured JSONL for post-hoc inspection.

Thread-affinity: every method runs on the cell's single execution thread (the streaming watchdog ticks
inline on that thread), so no locking is needed beyond what the emit sink already provides.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from ..terminal import TerminalChunk

_FILE_BATCH_CAP = 12   # at most this many file lines per batch; the rest are summarized
_LINE_CAP = 240        # trim a streamed agent line to keep the preview readable
_TREE_CAP = 60         # cap the rendered tree so a huge repo doesn't flood the stream
# CSI escape sequences (colour, cursor moves, screen/line clears). A CLI that redraws its UI on a piped
# stdout re-emits whole frames wrapped in these — stripping them + dropping the now-empty control lines
# (and consecutive exact repeats) collapses the "same thing streamed over and over" into real new lines.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[=>]|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _fmt_dur(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


class ProgressReporter:
    """Narrate a long build to a text sink + a structured JSONL history. Inert when `emit` is None."""

    def __init__(self, emit: Callable[[str | TerminalChunk], None] | None, *,
                 jsonl_path: Path | str | None = None,
                 label: str = "", heartbeat_s: int = 20) -> None:
        self._emit = emit
        self._label = label
        self._heartbeat_s = heartbeat_s
        self._jsonl = Path(jsonl_path) if jsonl_path else None
        self._seen_files: set[str] = set()
        self._start = time.monotonic()
        self._last_heartbeat = 0.0
        self._last_cli = ""  # last forwarded CLI line — suppress an immediate redraw repeat
        self._command_offsets: dict[str, int] = {}
        if self._jsonl is not None:
            try:
                self._jsonl.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._jsonl = None

    # ---- sinks ----------------------------------------------------------------
    def _say(self, text: str, *, stream_id: str = "terminal", stream_label: str = "terminal",
             stream_done: bool = False) -> None:
        if self._emit is not None:
            try:
                chunk = text if text.endswith("\n") else text + "\n"
                if stream_id == "terminal" and not stream_done:
                    self._emit(chunk)
                else:
                    self._emit(TerminalChunk(chunk, stream_id, stream_label, stream_done))
            except Exception:  # noqa: BLE001 — a broken sink must never break the build
                pass

    def _record(self, kind: str, **data: object) -> None:
        if self._jsonl is None:
            return
        row = {"t": round(time.time(), 3), "elapsed_s": round(time.monotonic() - self._start, 1),
               "kind": kind, **data}
        try:
            with self._jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        except OSError:
            pass

    # ---- structured milestones ------------------------------------------------
    def phase(self, title: str) -> None:
        self._say(f"\n▸ {title}")
        self._record("phase", title=title)

    def plan(self, milestones: list[str], layers: list[str] | None = None) -> None:
        self._say("  plan:")
        for line in milestones:
            self._say(f"    • {line}")
        if layers:
            self._say("  workflow (topological layers):")
            for line in layers:
                self._say(f"    └ {line}")
        self._record("plan", milestones=milestones, layers=layers or [])

    def pass_start(self, index: int, total: int) -> None:
        self._say(f"\n  ⟳ pass {index}/{total} — generating…")
        self._record("pass_start", index=index, total=total)

    def pass_result(self, index: int, total: int, *, satisfied: list[str], n_reqs: int,
                    newly: list[str], still_open: list[str], n_files: int, note: str = "") -> None:
        suffix = f" · {note}" if note else ""
        self._say(f"  ✓ pass {index}/{total}: {len(satisfied)}/{n_reqs} requirements evidenced · "
                  f"{n_files} files{suffix}")
        for req in newly:
            self._say(f"      ✚ {req}")
        if still_open:
            shown = ", ".join(still_open[:8]) + (" …" if len(still_open) > 8 else "")
            self._say(f"      · still open: {shown}")
        self._record("pass_result", index=index, total=total, satisfied=satisfied,
                     newly=newly, still_open=still_open, n_files=n_files, note=note)

    def files_seen(self, rels: list[str]) -> None:
        """Report files that appeared/changed in the live workspace since the last tick."""

        fresh = [rel for rel in rels if rel not in self._seen_files]
        self._seen_files.update(rels)
        if not fresh:
            return
        for rel in fresh[:_FILE_BATCH_CAP]:
            self._say(f"      ✚ wrote {rel}")
        if len(fresh) > _FILE_BATCH_CAP:
            self._say(f"      … +{len(fresh) - _FILE_BATCH_CAP} more files")
        self._record("files", added=fresh, total=len(self._seen_files))

    def tree(self, files: dict[str, str]) -> None:
        """Emit a compact snapshot of the current repo as an indented tree."""

        if not files:
            return
        self._say(f"  workspace ({len(files)} files):")
        for rel in sorted(files)[:_TREE_CAP]:
            depth = rel.count("/")
            self._say(f"    {'  ' * depth}{rel.rsplit('/', 1)[-1]}")
        if len(files) > _TREE_CAP:
            self._say(f"    … +{len(files) - _TREE_CAP} more")
        self._record("tree", n_files=len(files))

    def cli_line(self, line: str) -> None:
        """Forward a raw line of the underlying agent CLI's output (Claude-Code/Codex-style stream).

        Strips ANSI control sequences and collapses carriage-return redraws to the final segment, then
        drops empties and an immediate exact repeat — so a CLI that re-renders its UI frame each tick
        adds only genuinely new lines instead of streaming the same block over and over (reported bug)."""

        if self._codex_json(line):
            return
        text = _ANSI.sub("", line.split("\r")[-1]).strip()
        if not text or text == self._last_cli:
            return
        self._last_cli = text
        self._say(f"  │ {text[:_LINE_CAP]}")

    def _codex_json(self, line: str) -> bool:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(event, dict):
            return False
        item = event.get("item")
        if not isinstance(item, dict):
            return str(event.get("type", "")).startswith(("thread.", "turn."))
        if item.get("type") == "agent_message":
            text = str(item.get("text") or "").strip()
            if text:
                self._say(f"  │ {text[:_LINE_CAP]}")
            return True
        if item.get("type") != "command_execution":
            return True
        stream_id = f"codex:{item.get('id') or len(self._command_offsets)}"
        command = str(item.get("command") or "command")
        label = command if len(command) <= 36 else command[:33] + "..."
        if stream_id not in self._command_offsets:
            self._command_offsets[stream_id] = 0
            self._say(f"$ {command}", stream_id=stream_id, stream_label=label)
        output = str(item.get("aggregated_output") or "")
        offset = self._command_offsets[stream_id]
        if len(output) > offset:
            self._say(output[offset:], stream_id=stream_id, stream_label=label)
            self._command_offsets[stream_id] = len(output)
        if event.get("type") == "item.completed" or item.get("status") in {"completed", "failed"}:
            code = item.get("exit_code")
            self._say(f"[exit {code}]", stream_id=stream_id, stream_label=label, stream_done=True)
        return True

    def tick(self, idle_s: float, elapsed_s: float, n_files: int) -> None:
        """Heartbeat from the streaming watchdog: surface a 'still working' line when quiet."""

        if idle_s < self._heartbeat_s:
            return
        now = time.monotonic()
        if now - self._last_heartbeat < self._heartbeat_s:
            return
        self._last_heartbeat = now
        warn = "  ⚠ quiet" if idle_s >= self._heartbeat_s * 3 else ""
        self._say(f"      ⏱ still working · {n_files} files · last activity {int(idle_s)}s ago · "
                  f"elapsed {_fmt_dur(elapsed_s)}{warn}")
        self._record("heartbeat", idle_s=round(idle_s, 1), elapsed_s=round(elapsed_s, 1),
                     n_files=n_files)

    def note(self, message: str) -> None:
        self._say(f"      {message}")
        self._record("note", message=message)

    def verdict(self, *, passed: bool, satisfied: list[str], skipped: list[str]) -> None:
        mark = "complete" if passed else "incomplete"
        self._say(f"\n  ⏹ verdict: {mark} · {len(satisfied)} satisfied · {len(skipped)} open")
        if skipped:
            self._say(f"      open: {', '.join(skipped)}")
        self._record("verdict", passed=passed, satisfied=satisfied, skipped=skipped)
