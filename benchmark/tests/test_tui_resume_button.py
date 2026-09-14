"""In-TUI resume button + per-cell timestamps.

After a pause (an infra issue or a user pause) the user can press `r` to retry from the checkpoint
without leaving the TUI; if the issue persists it auto-pauses again with a "still couldn't" message.
The model stamps each cell's wall-clock start/finish for legibility during long/paused runs.
"""

from gauntlet.tui.app import GauntletApp
from gauntlet.tui.events import (
    CellFinished,
    CellRef,
    CellStarted,
    CellStatus,
    RunFinished,
    RunStarted,
)
from gauntlet.tui.model import ExperimentTree
from gauntlet.tui.render import cell_header
from gauntlet.tui.runner import CellSpec


def _app():
    specs = [CellSpec(CellRef("security", "g", "c0", "codex_cli_raw"), "Codex", "p", lambda e: None)]

    class _CP:
        from pathlib import Path
        path = Path("/tmp/_gauntlet_test/checkpoint.jsonl")

    app = GauntletApp("security", specs, finalize=None, checkpoint=_CP())
    app._set_status = lambda t: setattr(app, "_last_status", t)

    class _PB:
        def update(self, **k):
            pass
    app.query_one = lambda sel, kind=None: _PB()
    return app


def test_pause_offers_resume_then_resume_relaunches():
    app = _app()
    launched = {"n": 0}
    app._run_experiment = lambda: launched.__setitem__("n", launched["n"] + 1)
    app._tree_model.finished = True

    app.apply_event(RunFinished(passed=35, failed=0, errored=0, skipped=0, report_path=None,
                                paused=True, pause_reason="lost connectivity / transient API error"))
    assert app._paused and "press r to resume" in app._last_status

    app.action_resume()
    assert not app._paused and app._resumed_once and launched["n"] == 1
    assert app._tree_model.finished is False


def test_repause_reads_still_could_not():
    app = _app()
    app._run_experiment = lambda: None
    app._resumed_once = True  # already resumed once
    app.apply_event(RunFinished(passed=35, failed=0, errored=0, skipped=0, report_path=None,
                                paused=True, pause_reason="lost connectivity / transient API error"))
    assert "still" in app._last_status and "couldn't continue" in app._last_status


def test_resume_guarded_when_not_paused():
    app = _app()
    app._run_experiment = lambda: (_ for _ in ()).throw(AssertionError("should not run"))
    app._paused = False
    app.action_resume()  # no-op, must not relaunch
    assert "not paused" in app._last_status


def test_cells_carry_wall_clock_timestamps():
    t = ExperimentTree()
    ref = CellRef("security", "g", "c0", "codex_cli_raw")
    t.on_event(RunStarted(track="security", total=1, harnesses=[("codex_cli_raw", "Codex")]))
    t.on_event(CellStarted(ref=ref, harness_label="Codex", prompt="p"))
    cell = next(c for grp in t.groups for c in grp.cells)
    assert cell.started_at and len(cell.started_at.split(":")) == 3  # HH:MM:SS
    t.on_event(CellFinished(ref=ref, status=CellStatus.PASS, output="ok", detail={}, files={},
                            error=None, duration_ms=123))
    assert cell.finished_at
    from rich.console import Console
    con = Console(width=120, no_color=True)
    with con.capture() as cap:
        con.print(cell_header(cell))
    assert "→" in cap.get() and "123 ms" in cap.get()
