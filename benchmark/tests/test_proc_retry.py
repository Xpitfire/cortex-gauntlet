"""_proc.run: self-heal the transient threaded fork/exec fd race, surface persistent failures safely."""

import subprocess

import pytest

from gauntlet.analysis import _proc


def test_retries_transient_fd_race_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake(argv, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("bad value(s) in fds_to_keep")  # the transient CPython race
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake)
    result = _proc.run(["x"], retries=3, backoff=0)
    assert result.returncode == 0 and result.stdout == "ok" and calls["n"] == 3


def test_unrelated_valueerror_is_not_swallowed(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (_ for _ in ()).throw(ValueError("nope")))
    with pytest.raises(ValueError, match="nope"):  # a real bug must propagate, not be retried
        _proc.run(["x"], retries=2, backoff=0)


def test_persistent_fd_race_degrades_to_subprocesserror(monkeypatch):
    def fake(argv, **kw):
        raise ValueError("bad value(s) in fds_to_keep")

    monkeypatch.setattr(subprocess, "run", fake)
    # callers catch (SubprocessError, OSError) and degrade gracefully — never a raw ValueError escaping
    with pytest.raises(subprocess.SubprocessError):
        _proc.run(["x"], retries=2, backoff=0)


def test_success_passes_through(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "hi", ""))
    assert _proc.run(["x"]).stdout == "hi"
