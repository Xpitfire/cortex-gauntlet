"""M6 signal sources: FileSignalSource (benchmark/no-network) + GhSignalSource (GATED OFF).

Hermetic: the file source reads a tmp JSON fixture; the gh source is never enabled, so no subprocess
or network call is made. A subprocess guard proves the disabled gh path runs nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("synapse.domain.signals")

from gauntlet.synapse_ports import FileSignalSource, GhSignalSource
from synapse.domain.signals import SignalCursor, SignalKind


def _cursor(*seen: str) -> SignalCursor:
    return SignalCursor(seen_ids=set(seen))


def test_file_source_reads_fixture(tmp_path: Path):
    fixture = [
        {"id": "s1", "kind": "pr_comment", "source": "gh:pr:7",
         "unit_id": "u1", "payload": {"body": "please fix"}},
        {"id": "s2", "kind": "ci_status", "source": "ci", "payload": {"state": "failed"}},
        {"id": "s3", "kind": "approval", "source": "gh:pr:7"},
    ]
    path = tmp_path / "signals.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    signals = FileSignalSource(path).poll(_cursor())
    assert [s.id for s in signals] == ["s1", "s2", "s3"]  # deterministic file order
    assert signals[0].kind is SignalKind.PR_COMMENT
    assert signals[0].source == "gh:pr:7"
    assert signals[0].unit_id == "u1"
    assert signals[0].payload == {"body": "please fix"}
    assert signals[1].kind is SignalKind.CI_STATUS
    assert signals[2].kind is SignalKind.APPROVAL
    assert signals[2].payload == {}  # tolerated missing payload


def test_file_source_unknown_kind_falls_back_to_custom(tmp_path: Path):
    path = tmp_path / "signals.json"
    path.write_text(json.dumps([{"id": "x", "kind": "not_a_kind", "source": "z"}]), encoding="utf-8")
    signals = FileSignalSource(path).poll(_cursor())
    assert signals[0].kind is SignalKind.CUSTOM


def test_file_source_skips_seen_ids(tmp_path: Path):
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps([{"id": "a", "kind": "timer", "source": "t"},
                    {"id": "b", "kind": "timer", "source": "t"}]),
        encoding="utf-8",
    )
    signals = FileSignalSource(path).poll(_cursor("a"))
    assert [s.id for s in signals] == ["b"]


def test_file_source_skips_records_without_id(tmp_path: Path):
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps([{"kind": "timer", "source": "t"},  # no id → skipped
                    {"id": "ok", "kind": "timer", "source": "t"}]),
        encoding="utf-8",
    )
    signals = FileSignalSource(path).poll(_cursor())
    assert [s.id for s in signals] == ["ok"]


def test_file_source_missing_file_is_empty(tmp_path: Path):
    assert FileSignalSource(tmp_path / "nope.json").poll(_cursor()) == []


def test_file_source_empty_file_is_empty(tmp_path: Path):
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    assert FileSignalSource(path).poll(_cursor()) == []


def test_file_source_invalid_json_is_empty(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert FileSignalSource(path).poll(_cursor()) == []


# --- GhSignalSource: GATED OFF, no network ----------------------------------------------------
def test_gh_source_disabled_returns_empty():
    assert GhSignalSource("42", enabled=False).poll(_cursor()) == []


def test_gh_source_default_is_disabled():
    # enabled defaults to False → still no signals, no gh.
    assert GhSignalSource("42").poll(_cursor()) == []


def test_gh_source_disabled_never_invokes_subprocess(monkeypatch):
    import gauntlet.synapse_ports.signal_source as mod

    def _boom(*args, **kwargs):
        raise AssertionError("gh source must NOT invoke subprocess while disabled")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    assert GhSignalSource("42", enabled=False).poll(_cursor()) == []  # proves no subprocess call
