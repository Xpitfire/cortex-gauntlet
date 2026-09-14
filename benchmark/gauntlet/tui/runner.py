"""ExperimentRunner — run cells one at a time with per-cell exception isolation.

Each cell is a `CellSpec` whose `run(emit_output)` performs the work and returns a `CellOutcome`.
The runner times it, streams its output via the bus, and — critically — catches any exception so a
single failing experiment becomes an ERROR cell (with traceback) instead of aborting the whole run.
Reusable for any experiment: supply specs + an optional finalize step.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..errors import AssetUnsupported, EvaluationUnavailable, HarnessTimeout, RedTeamError
from ..resilience import is_infra_error
from ..terminal import TerminalChunk
from .events import (
    CellFinished,
    CellOutput,
    CellRef,
    CellStarted,
    CellStatus,
    EventBus,
    RunFinished,
    RunStarted,
)

if TYPE_CHECKING:
    from ..resilience import Checkpoint


@dataclass(slots=True)
class CellOutcome:
    """Result of running a cell: terminal status, the captured artifact, and detail fields."""

    status: CellStatus
    output: str = ""
    detail: dict[str, str] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)  # generated files to browse in the editor
    result: object | None = None  # raw result object, used by finalize (e.g. to build a RunRecord)


def _result_class(track: str):
    """The result dataclass for a track, so a checkpointed `result` can be rebuilt on resume (lazy
    imports avoid pulling every track's deps). None → restore display-only (no runrecord row)."""
    try:
        if track == "security":
            from ..models import CaseResult
            return CaseResult
        if track == "quality":
            from ..quality.models import QualityResult
            return QualityResult
        if track == "repo":
            from ..repo.models import RepoResult
            return RepoResult
        if track == "generative":
            from ..generative.models import GenerativeResult
            return GenerativeResult
        if track == "project":
            from ..project.models import ProjectResult
            return ProjectResult
    except ImportError:
        return None
    return None


_DISPLAY_CAP = 100_000  # cap a recovered display string so the TUI editor never chokes on a huge artifact


def _display_from_result(track: str, result: object) -> tuple[str, dict[str, str]]:
    """Best-effort (output, files) for the editor recovered from a checkpointed result dataclass.

    Some checkpoints (older runs, or assembled `*-corrected` checkpoints) persist the full `result`
    but leave the display `output`/`files` empty, so a resumed cell would show a blank
    "restored from checkpoint" view even though the model's work is on disk. Recover the artifact
    from the result so resume shows it. Never raises — display recovery must not break a resume."""

    def cap(text: str) -> str:
        return text if len(text) <= _DISPLAY_CAP else text[:_DISPLAY_CAP] + "\n…(truncated)\n"

    try:
        if track in ("quality", "generative"):
            code = cap(str(getattr(result, "code", "") or ""))
            files = {p: cap(str(c)) for p, c in (getattr(result, "files", {}) or {}).items()}
            if not files and code:
                files = {"solution.py": code}
            test_output = getattr(result, "test_output", "") or ""
            if test_output:
                files["_test_output.txt"] = cap(str(test_output))
            return code, files
        if track == "project":
            return "", {p: cap(str(c)) for p, c in (getattr(result, "files", {}) or {}).items()}
        if track == "repo":
            return (
                cap(str(getattr(result, "test_output", "") or "")),
                {p: cap(str(c)) for p, c in (getattr(result, "files", {}) or {}).items()},
            )
        if track == "security":
            transcript = getattr(result, "transcript", None)
            return (cap(str(getattr(transcript, "response", "") or "")) if transcript else ""), {}
    except Exception:  # noqa: BLE001 — display recovery must never break a resume
        return "", {}
    return "", {}


def _restore(stored: dict) -> CellOutcome:
    """Rebuild a CellOutcome from a checkpoint record. When a serialized `result` is present (every
    run now persists it), deserialize it so finalize includes this cell in the runrecord — a resumed
    run rebuilds a COMPLETE report, and the checkpoint is a full, post-analyzable record. The display
    `output`/`files` are backfilled from that result when the checkpoint left them empty, so a resumed
    cell shows the model's work rather than a blank view."""

    result = None
    cls = _result_class(stored.get("result_track", ""))
    if stored.get("result") and cls is not None:
        from ..models import dataclass_from_dict
        try:
            result = dataclass_from_dict(cls, stored["result"])
        except (TypeError, KeyError, ValueError):  # an edited/partial result → restore display-only
            result = None
    output = stored.get("output", "") or ""
    files = dict(stored.get("files", {}) or {})
    if (not output or not files) and result is not None:
        derived_output, derived_files = _display_from_result(stored.get("result_track", ""), result)
        output = output or derived_output
        files = files or derived_files
    return CellOutcome(
        status=CellStatus(stored.get("status", "skip")), output=output,
        detail=dict(stored.get("detail", {})), files=files, result=result,
    )


def _retryable_exception_reason(text: str) -> str:
    lower = text.lower()
    if "claude judge returned no parseable json" in lower or "cortex judge returned no parseable json" in lower:
        return "semantic judge returned no parseable JSON — fix the judge/provider limit, then resume"
    if "timeoutexpired" in lower or "timed out after" in lower:
        return "subprocess timed out — resume to retry this cell"
    if is_infra_error(text):
        return "provider infrastructure error — resume after it clears"
    return ""


# run(emit_output) -> CellOutcome ; emit_output streams a chunk to the cell's terminal preview
CellRun = Callable[[Callable[[str | TerminalChunk], None]], CellOutcome]
# finalize receives (spec, outcome, error) for every cell (error is the traceback for ERROR cells)
Finalize = Callable[[list[tuple["CellSpec", CellOutcome, str | None]]], str | None]


@dataclass(slots=True)
class CellSpec:
    """A runnable cell: its address, the harness label, a display prompt, and the work to do."""

    ref: CellRef
    harness_label: str
    prompt: str
    run: CellRun


class _RunState:
    """Lock-guarded accumulators shared by the serial and parallel run paths: the status tally, the
    (spec, outcome, error) pairs finalize consumes, and the pause flag/reason. One lock serializes the
    few mutations (tally increments, pairs append, checkpoint append) so concurrent provider arms can
    never corrupt them or interleave a checkpoint line."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tally: dict[CellStatus, int] = {
            CellStatus.PASS: 0, CellStatus.FAIL: 0, CellStatus.ERROR: 0, CellStatus.SKIP: 0}
        self.pairs: list[tuple[CellSpec, CellOutcome, str | None]] = []
        self.paused = False
        self.pause_reason = ""


class ExperimentRunner:
    """Drive a list of cells, emitting realtime events; one cell's failure never aborts the run."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._pause = threading.Event()  # set to pause gracefully after the current cell

    def request_pause(self) -> None:
        """Ask the run to pause AFTER the current cell finishes (it is checkpointed first, so nothing
        fails or is lost). The remaining cells resume later. Triggered by the TUI 'p' key, a SIGINT, or
        the `pause` CLI command (which drops a PAUSE sentinel the loop also watches)."""
        self._pause.set()

    def run(
        self, track: str, specs: list[CellSpec], finalize: Finalize | None = None,
        checkpoint: "Checkpoint | None" = None, workers: int = 1,
    ) -> RunFinished:
        """Run the cells. With a `checkpoint`, completed cells are persisted and replayed on resume;
        a persistent rate limit pauses the run (checkpoint kept, that cell not recorded) instead of
        marking it failed — resume re-runs from there once the limit clears.

        `workers > 1` runs the independent provider arms concurrently (one thread per harness, so each
        provider's cells stay serial — its adapter is single-threaded and its API is never hammered in
        parallel — while DIFFERENT providers overlap), bounded to `workers` in-flight cells. `workers
        <= 1` is the original strictly-serial path, byte-for-byte unchanged."""

        harnesses = list(dict.fromkeys((s.ref.harness_id, s.harness_label) for s in specs))
        self.bus.emit(RunStarted(track=track, total=len(specs), harnesses=harnesses))
        # a checkpoint cell whose status was edited to "rerun" is treated as NOT done, so the user can
        # mark individual cells to re-run (e.g. ones they judge broken) and resume to redo just those.
        done = {k: v for k, v in (checkpoint.completed() if checkpoint else {}).items()
                if (v or {}).get("status") != "rerun"}
        # a PAUSE sentinel beside the checkpoint lets `cortex benchmark pause <run-id>` request a pause
        # from another terminal. Clear a stale one on (re)start so a resumed run doesn't instantly pause.
        pause_file = (checkpoint.path.parent / "PAUSE") if checkpoint is not None else None
        if pause_file is not None and pause_file.exists():
            pause_file.unlink()

        state = _RunState()
        if workers > 1 and len(specs) > 1:
            self._run_parallel(specs, done, checkpoint, pause_file, state, workers)
        else:
            self._run_serial(specs, done, checkpoint, pause_file, state)

        report_path = None if state.paused else self._finalize(finalize, state.pairs)
        finished = RunFinished(
            passed=state.tally[CellStatus.PASS], failed=state.tally[CellStatus.FAIL],
            errored=state.tally[CellStatus.ERROR], skipped=state.tally[CellStatus.SKIP],
            report_path=report_path, paused=state.paused, pause_reason=state.pause_reason,
        )
        self.bus.emit(finished)
        return finished

    def _run_serial(self, specs: list[CellSpec], done: dict, checkpoint: "Checkpoint | None",
                    pause_file, state: _RunState) -> None:
        """Strictly-serial execution (the original behaviour): one cell at a time, in spec order."""
        for spec in specs:
            # user-requested pause (TUI 'p' / SIGINT / `pause` CLI): stop BEFORE the next cell — the
            # previous cell is already checkpointed, so nothing fails or is lost; resume continues here.
            if self._should_pause(spec.ref, pause_file, state):
                break
            if self._handle_cell(spec, done, checkpoint, state):  # infra pause → stop
                break

    def _run_parallel(self, specs: list[CellSpec], done: dict, checkpoint: "Checkpoint | None",
                      pause_file, state: _RunState, workers: int) -> None:
        """Run cells across provider arms concurrently. Cells are grouped by harness id and each group
        is drained by its own thread, so a given provider's cells run serially (its adapter is touched
        by one thread only, and one provider's API is never called in parallel) while different
        providers overlap. A semaphore caps total in-flight cells at `workers`, so concurrency stays
        bounded even with many arms. A user pause, or an infra pause raised by any arm, stops new cells
        from starting; cells already running finish and are checkpointed, so nothing is lost."""

        groups: dict[str, list[CellSpec]] = {}
        for spec in specs:
            groups.setdefault(spec.ref.harness_id, []).append(spec)
        slots = threading.Semaphore(max(1, workers))

        def drain(group_specs: list[CellSpec]) -> None:
            for spec in group_specs:
                if self._should_pause(spec.ref, pause_file, state):
                    return
                with slots:
                    if state.paused:  # another arm paused while we waited for a free slot
                        return
                    if self._handle_cell(spec, done, checkpoint, state):  # this cell hit an infra pause
                        return

        threads = [threading.Thread(target=drain, args=(g,), name=f"arm:{hid}", daemon=True)
                   for hid, g in groups.items()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def _should_pause(self, ref: CellRef, pause_file, state: _RunState) -> bool:
        """True if no new cell should start: a user pause (TUI 'p' / SIGINT / PAUSE sentinel) or an
        infra pause already raised elsewhere. The user pause is announced once and is checkpoint-safe
        (the previous cell is already persisted), so a resume continues from here."""
        if state.paused:
            return True
        if not (self._pause.is_set() or (pause_file is not None and pause_file.exists())):
            return False
        with state.lock:
            first = not state.paused
            if first:
                state.paused = True
                state.pause_reason = "paused by user — resume to continue the remaining cells"
        if first:
            self.bus.emit(CellOutput(ref=ref, chunk="paused by user — run not failed\n"))
        return True

    def _handle_cell(self, spec: CellSpec, done: dict, checkpoint: "Checkpoint | None",
                     state: _RunState) -> bool:
        """Run (or restore) one cell and record its outcome under the shared lock. Returns True if the
        cell hit an INFRA failure (rate limit / auth loss / lost connectivity) that should pause the
        run — that cell is NOT recorded so a resume re-runs exactly it."""

        key = spec.ref.key
        if key in done:  # resume: replay the cached outcome without re-running the cell
            outcome = _restore(done[key])
            self.bus.emit(CellStarted(ref=spec.ref, harness_label=spec.harness_label, prompt=spec.prompt))
            with state.lock:
                state.tally[outcome.status] = state.tally.get(outcome.status, 0) + 1
                state.pairs.append((spec, outcome, None))
            self.bus.emit(CellFinished(
                ref=spec.ref, status=outcome.status,
                output=outcome.output or "restored from checkpoint\n",
                detail=outcome.detail, files=outcome.files, error=None, duration_ms=0))
            return False
        self.bus.emit(CellStarted(ref=spec.ref, harness_label=spec.harness_label, prompt=spec.prompt))
        started = time.monotonic()
        outcome, error = self._run_one(spec)
        duration_ms = int((time.monotonic() - started) * 1000)
        # pause (don't record this cell, resume re-runs it) on any INFRA failure — a rate limit, an
        # auth loss (CLI logged out), or lost connectivity / a transient API error. Never a task
        # pass/fail: the user fixes it (reconnect / re-auth) and resumes to retry exactly this cell.
        if outcome.detail.get("pause") or outcome.detail.get("rate_limited") or outcome.detail.get("auth_failed"):
            with state.lock:
                if not state.paused:
                    state.paused = True
                    state.pause_reason = outcome.detail.get("error") or "provider rate limit"
                reason = state.pause_reason
            self.bus.emit(CellOutput(ref=spec.ref, chunk=f"paused: {reason} — run not failed\n"))
            return True
        with state.lock:
            state.tally[outcome.status] = state.tally.get(outcome.status, 0) + 1
            state.pairs.append((spec, outcome, error))
        self.bus.emit(CellFinished(
            ref=spec.ref, status=outcome.status, output=outcome.output,
            detail=outcome.detail, files=outcome.files, error=error, duration_ms=duration_ms,
        ))
        if checkpoint is not None:
            # persist the FULL scored result (every track) so the checkpoint is a complete,
            # post-analyzable record AND a resume can rebuild a complete runrecord including
            # already-done cells — not just the re-run ones.
            stored = {"status": outcome.status.value, "output": outcome.output,
                      "detail": outcome.detail, "files": outcome.files}
            if outcome.result is not None:
                from dataclasses import asdict, is_dataclass
                if is_dataclass(outcome.result):
                    stored["result"] = asdict(outcome.result)
                    stored["result_track"] = spec.ref.track
            with state.lock:  # serialize checkpoint appends so concurrent arms never interleave a line
                checkpoint.put(key, stored)
        return False

    def _run_one(self, spec: CellSpec) -> tuple[CellOutcome, str | None]:
        try:
            outcome = spec.run(lambda chunk: self.bus.emit(self._output_event(spec.ref, chunk)))
            return outcome, None
        except HarnessTimeout as exc:  # transient timeout: pause without checkpointing so resume retries it
            reason = f"harness timed out — resume to retry this cell: {exc}"
            return CellOutcome(status=CellStatus.ERROR, detail={"pause": "1", "timeout": "1", "error": reason}), None
        except AssetUnsupported as exc:  # harness can't receive the asset → SKIPPED (never saw the payload)
            return CellOutcome(status=CellStatus.SKIP, detail={"skipped": "unsupported", "reason": str(exc)}), None
        except RedTeamError as exc:  # configured red-team produced no follow-up turn → SKIPPED, not scored
            return CellOutcome(status=CellStatus.SKIP, detail={"skipped": "redteam", "reason": str(exc)}), None
        except EvaluationUnavailable as exc:
            return CellOutcome(
                status=CellStatus.SKIP,
                detail={"skipped": "infrastructure", "reason": str(exc)},
            ), None
        except Exception:  # isolate: a failing experiment is data, not a crash
            tb = traceback.format_exc()
            reason = _retryable_exception_reason(tb)
            if reason:
                return CellOutcome(status=CellStatus.ERROR, detail={"pause": "1", "retryable": "1", "error": reason}), tb
            return CellOutcome(status=CellStatus.ERROR), tb

    @staticmethod
    def _output_event(ref: CellRef, chunk: str | TerminalChunk) -> CellOutput:
        if isinstance(chunk, TerminalChunk):
            return CellOutput(ref=ref, chunk=chunk.chunk, stream_id=chunk.stream_id,
                              stream_label=chunk.stream_label, stream_done=chunk.stream_done)
        return CellOutput(ref=ref, chunk=chunk)

    def _finalize(self, finalize: Finalize | None, pairs: list[tuple[CellSpec, CellOutcome | None]]) -> str | None:
        if finalize is None:
            return None
        try:
            return finalize(pairs)
        except Exception:  # finalize (report/aggregate) must not crash the UI either
            traceback.print_exc()
            return None
