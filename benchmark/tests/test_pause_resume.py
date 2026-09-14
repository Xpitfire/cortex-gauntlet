"""User-initiated pause + auto-pause on infra errors + complete/editable checkpoints.

A run must pause (never fail) on a user request, a lost connection, an auth loss, or a rate limit, and
resume exactly where it left off. The checkpoint must carry each cell's full scored result so a resume
rebuilds a complete report and the file is post-analyzable / editable (set a cell to "rerun" to redo it).
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

from gauntlet.models import dataclass_from_dict
from gauntlet.repo.models import RepoResult
from gauntlet.resilience import is_auth_error, is_connection_error, is_infra_error, is_rate_limited
from gauntlet.tui.bridge import _infra_pause
from gauntlet.tui.events import CellRef, CellStatus, EventBus
from gauntlet.tui.runner import CellOutcome, CellSpec, ExperimentRunner, _restore


def _cp():
    from gauntlet.resilience import Checkpoint
    d = Path(tempfile.mkdtemp())
    return d, Checkpoint(d / "checkpoint.jsonl")


def _spec(i, on_run=None, result=None):
    def run(_emit):
        if on_run:
            on_run(i)
        return CellOutcome(status=CellStatus.PASS, output=f"c{i}", detail={}, files={}, result=result)
    return CellSpec(CellRef("security", "g", f"c{i}", "codex_cli_raw"), "Codex", "p", run)


def test_connection_and_infra_error_detection():
    assert is_connection_error("Connection reset by peer") and is_infra_error("ETIMEDOUT")
    assert not is_connection_error("here is the offline-first cache")  # content, not an outage
    assert is_auth_error("401 Invalid authentication credentials")
    assert is_rate_limited("429 too many requests")


def test_infra_pause_returns_a_pause_outcome_for_each_infra_class():
    for txt, flag in [("Failed to authenticate. 401", "auth_failed"),
                      ("Connection reset by peer", "connection_lost"),
                      ("429 rate limit exceeded", "rate_limited")]:
        out = _infra_pause(txt, lambda _c: None)
        assert out is not None and out.detail.get("pause") == "1" and out.detail.get(flag) == "1"
    assert _infra_pause("here is your solution", lambda _c: None) is None


def test_user_pause_sentinel_stops_then_resumes():
    d, cp = _cp()
    ran = []
    specs = [_spec(i, on_run=lambda i: (ran.append(i), (d / "PAUSE").write_text("x") if i == 1 else None))
             for i in range(5)]
    fin = ExperimentRunner(EventBus()).run("security", specs, None, checkpoint=cp)
    assert fin.paused and len(cp.completed()) == 2  # cells 0,1 ran + checkpointed; paused before 2
    ran.clear()
    fin2 = ExperimentRunner(EventBus()).run("security", specs, None, checkpoint=cp)  # PAUSE cleared on restart
    assert not fin2.paused and ran == [2, 3, 4] and len(cp.completed()) == 5


def test_auto_pause_on_infra_outcome_does_not_checkpoint_the_cell():
    d, cp = _cp()
    def boom(_emit):
        return CellOutcome(status=CellStatus.ERROR, detail={"pause": "1", "error": "lost connectivity"})
    specs = [_spec(0), CellSpec(CellRef("security", "g", "c1", "codex_cli_raw"), "Codex", "p", boom), _spec(2)]
    fin = ExperimentRunner(EventBus()).run("security", specs, None, checkpoint=cp)
    assert fin.paused and "lost connectivity" in fin.pause_reason
    assert set(cp.completed()) == {specs[0].ref.key}  # the infra cell + the rest are NOT recorded


def test_rerun_status_in_checkpoint_is_re_run_on_resume():
    d, cp = _cp()
    ran = []
    specs = [_spec(i, on_run=ran.append) for i in range(3)]
    ExperimentRunner(EventBus()).run("security", specs, None, checkpoint=cp)
    # edit the checkpoint: mark cell c1 to "rerun"
    lines = (d / "checkpoint.jsonl").read_text().splitlines()
    import json
    edited = [json.loads(x) for x in lines]
    for rec in edited:
        if rec["key"].endswith("/c1") or "c1" in rec["key"]:
            rec["outcome"]["status"] = "rerun"
    (d / "checkpoint.jsonl").write_text("\n".join(json.dumps(r) for r in edited) + "\n")
    ran.clear()
    ExperimentRunner(EventBus()).run("security", specs, None, checkpoint=cp)
    assert len(ran) == 1  # only the cell edited to "rerun" re-ran


def test_checkpoint_stores_full_result_for_any_track_and_restores_it():
    rr = RepoResult(task_id="t", harness_id="h", resolved=True, tests_passed=3, tests_total=3,
                    backend="b", code_quality=0.8, lint_issues=2, type_errors=1)
    stored = {"status": "pass", "output": "", "detail": {}, "files": {},
              "result": asdict(rr), "result_track": "repo"}
    outcome = _restore(stored)
    assert outcome.result is not None and outcome.result.resolved and outcome.result.code_quality == 0.8
    # generic round-trip preserves nested values
    assert dataclass_from_dict(RepoResult, asdict(rr)).type_errors == 1


def test_display_from_result_recovers_quality_artifact():
    """A checkpoint that kept only the result (empty display output/files) still yields the
    model's code + files for the editor — the quality-track resume bug."""
    from gauntlet.tui.runner import _display_from_result

    class _R:  # duck-typed QualityResult (only the attributes the recovery reads)
        code = "def f():\n    return 1\n"
        files = {"solution.py": "def f():\n    return 1\n", "test_solution.py": "assert f() == 1\n"}
        test_output = "1 passed\n"

    output, files = _display_from_result("quality", _R())
    assert "def f()" in output
    assert set(files) == {"solution.py", "test_solution.py", "_test_output.txt"}


def test_display_from_result_quality_solution_fallback_when_no_files():
    from gauntlet.tui.runner import _display_from_result

    class _R:
        code = "print('x')\n"
        files: dict[str, str] = {}
        test_output = ""

    output, files = _display_from_result("quality", _R())
    assert output == "print('x')\n" and files == {"solution.py": "print('x')\n"}


def test_restore_backfills_display_output_from_result_when_empty():
    """`_restore` recovers the editor output/files from the persisted result when the checkpoint
    left the display fields empty (older / *-corrected checkpoints) — fixes the blank resume view."""
    rr = RepoResult(task_id="t", harness_id="h", resolved=True, tests_passed=3, tests_total=3,
                    backend="b", files={"src/app.py": "print('hi')\n"}, test_output="3 passed\n")
    stored = {"status": "pass", "output": "", "detail": {}, "files": {},
              "result": asdict(rr), "result_track": "repo"}
    outcome = _restore(stored)
    assert outcome.output == "3 passed\n"          # repo track -> output recovered from test_output
    assert outcome.files == {"src/app.py": "print('hi')\n"}  # files recovered from the result
