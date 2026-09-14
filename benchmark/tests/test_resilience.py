"""Rate-limit resilience: a rate limit is never recorded as a task failure — it is retried with
backoff, surfaced distinctly, and (if persistent) pauses a checkpointed run that can later resume."""

import stat
from pathlib import Path

import gauntlet.livegen.adapters as ad
import gauntlet.livegen.base as base
from gauntlet.livegen.adapters import CodexCodeGen
from gauntlet.livegen.models import CodeGenRequest
from gauntlet.resilience import (
    Checkpoint,
    backoff_delays,
    is_rate_limited,
    rate_limit_retry,
)
from gauntlet.run import PRESETS
from gauntlet.tui.events import CellRef, CellStatus, EventBus
from gauntlet.tui.model import ExperimentTree
from gauntlet.tui.runner import CellOutcome, CellSpec, ExperimentRunner


def test_classifier_distinguishes_rate_limits_from_real_errors():
    for hit in ("HTTP 429 Too Many Requests", "rate_limit_exceeded", "Error: overloaded (529)",
                "quota exceeded", "please retry after 30s", "RESOURCE_EXHAUSTED"):
        assert is_rate_limited(hit), hit
    for miss in ("", "SyntaxError: invalid syntax", "ModuleNotFoundError: solution",
                 "auth profile uses oauth, needs an API key"):
        assert not is_rate_limited(miss), miss


def test_backoff_is_exponential_and_capped():
    assert backoff_delays(0) == []
    assert backoff_delays(3, base=5, cap=60) == [5, 10, 20]
    assert backoff_delays(5, base=20, cap=60) == [20, 40, 60, 60, 60]  # capped


def test_smart_default_and_env_override(monkeypatch):
    from gauntlet.resilience import DEFAULT_RATELIMIT_RETRIES, rate_limit_retries
    monkeypatch.delenv("GAUNTLET_RATELIMIT_RETRIES", raising=False)
    assert rate_limit_retries() == DEFAULT_RATELIMIT_RETRIES == 3          # smart default
    assert int(sum(backoff_delays(rate_limit_retries()))) == 35           # ~35s before pausing
    monkeypatch.setenv("GAUNTLET_RATELIMIT_RETRIES", "0")
    assert rate_limit_retries() == 0                                      # `--rate-limit-retries 0` → pause now
    monkeypatch.setenv("GAUNTLET_RATELIMIT_RETRIES", "garbage")
    assert rate_limit_retries() == DEFAULT_RATELIMIT_RETRIES              # bad value falls back to the default


def test_rate_limit_retry_recovers_then_gives_up():
    calls = {"n": 0}
    def limited_twice():
        calls["n"] += 1
        return "429" if calls["n"] < 3 else "ok"
    result, limited = rate_limit_retry(limited_twice, lambda r: r == "429", retries=5, sleep=lambda _: None)
    assert result == "ok" and not limited and calls["n"] == 3
    # never recovers within budget → reports still-limited (the caller pauses, not fails)
    result, limited = rate_limit_retry(lambda: "429", lambda r: r == "429", retries=2, sleep=lambda _: None)
    assert result == "429" and limited


def test_checkpoint_roundtrip_and_resume(tmp_path):
    ck = Checkpoint(tmp_path / "checkpoint.jsonl")
    assert ck.completed() == {}
    ck.put("t/g/a/h", {"status": "pass", "output": "x"})
    ck.put("t/g/b/h", {"status": "fail"})
    done = Checkpoint(tmp_path / "checkpoint.jsonl").completed()  # re-read from disk
    assert set(done) == {"t/g/a/h", "t/g/b/h"} and done["t/g/a/h"]["status"] == "pass"


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_adapter_flags_rate_limit_instead_of_failing(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_RATELIMIT_RETRIES", "0")  # no backoff sleeps in the test
    codex = _stub(tmp_path / "codex", "import sys; sys.stderr.write('Error 429: rate limit exceeded\\n')\n")
    monkeypatch.setattr(base.shutil, "which", lambda n: str(codex) if n == "codex" else None)
    monkeypatch.setattr(ad.shutil, "which", lambda n: str(codex) if n == "codex" else None)
    res = CodexCodeGen(PRESETS["codex_cli_raw"]).generate(
        CodeGenRequest(prompt="p", language="python", main_file="solution.py", timeout_s=5))
    assert res.rate_limited and not res.ok and "rate limited" in res.error  # flagged, not "no file produced"


# ── runner: resume skips done cells; a rate-limited cell pauses (does not fail) the run ───────────
def _spec(name, fn):
    return CellSpec(CellRef("t", "g", name, "h"), "h", f"prompt {name}", fn)


def _ok(emit):
    return CellOutcome(CellStatus.PASS, output="done")


def _ratelimited(emit):
    emit("hit a limit\n")
    return CellOutcome(CellStatus.ERROR, detail={"rate_limited": "1", "error": "rate limited: 429"})


def _run(specs, checkpoint=None):
    bus = EventBus()
    tree = ExperimentTree()
    bus.subscribe(tree)
    finished = ExperimentRunner(bus).run("t", specs, checkpoint=checkpoint)
    return tree, finished


def test_runner_pauses_on_rate_limit_without_failing(tmp_path):
    ck = Checkpoint(tmp_path / "cp.jsonl")
    ran = []
    tree, finished = _run([
        _spec("a", lambda e: ran.append("a") or _ok(e)),
        _spec("b", lambda e: ran.append("b") or _ratelimited(e)),
        _spec("c", lambda e: ran.append("c") or _ok(e)),
    ], checkpoint=ck)
    assert finished.paused and "rate limited" in finished.pause_reason
    assert ran == ["a", "b"]  # paused at b; c never ran
    assert finished.failed == 0 and finished.errored == 0  # the rate limit is NOT a failure
    done = ck.completed()
    assert "t/g/a/h" in done and "t/g/b/h" not in done  # b not checkpointed → resume re-runs it


def test_runner_resumes_completed_cells_from_checkpoint(tmp_path):
    ck = Checkpoint(tmp_path / "cp.jsonl")
    ck.put("t/g/a/h", {"status": "pass", "output": "cached", "detail": {}, "files": {}})
    ran = []
    tree, finished = _run([
        _spec("a", lambda e: ran.append("a") or _ok(e)),  # already done → must be skipped
        _spec("b", lambda e: ran.append("b") or _ok(e)),
    ], checkpoint=ck)
    assert ran == ["b"] and finished.passed == 2  # a restored, b run; both count
