"""Live judged tracks use semantic Claude judges by default."""

import json

import gauntlet.cli as cli
from gauntlet.run import resolve_security_judge, resolve_track_judge


class _Record:
    def to_json(self) -> str:
        return json.dumps({
            "track": "security",
            "config": {"seeds": 1},
            "cases": [],
            "results": [],
            "containment": {"payloads_executed": 0},
            "aggregates": {"per_harness": {}},
        })

    def to_dict(self) -> dict:
        return json.loads(self.to_json())


def test_security_auto_judge_resolution():
    assert resolve_security_judge("auto", live=True) == "claude"
    assert resolve_security_judge("auto", live=False) == "heuristic"
    assert resolve_security_judge("cortex", live=True) == "cortex"
    for track in ("security", "quality", "generative", "repo"):
        assert resolve_track_judge(track, "auto", live=True) == "claude"
        assert resolve_track_judge(track, "auto", live=False) == "heuristic"


def test_headless_live_security_auto_uses_claude_judge(monkeypatch, tmp_path):
    captured = {}

    def run_suite(**kwargs):
        captured.update(kwargs)
        return _Record()

    monkeypatch.setattr(cli, "run_suite", run_suite)
    monkeypatch.setattr(cli, "build_report", lambda _record, path: path.write_text("<html></html>"))
    monkeypatch.setattr(cli, "_print_summary", lambda _record: None)

    cli._execute_track(
        "security", run_id="x", out_dir=tmp_path, live=True, provider="codex", judge="auto",
        seeds=1, held_out=False, suite="security", adapters="", only=(), limit=0,
        network_policy="none", vision_judge="heuristic", synapse_iterations=1, vertex_ref="auto",
    )

    assert captured["judge_name"] == "claude"


def test_headless_live_quality_auto_uses_claude_judge(monkeypatch, tmp_path):
    captured = {}

    def run_quality_suite(**kwargs):
        captured.update(kwargs)
        return _Record()

    monkeypatch.setattr(cli, "run_quality_suite", run_quality_suite)
    monkeypatch.setattr(cli, "build_report", lambda _record, path: path.write_text("<html></html>"))
    monkeypatch.setattr(cli, "_print_quality_summary", lambda _record: None)

    cli._execute_track(
        "quality", run_id="x", out_dir=tmp_path, live=True, provider="codex", judge="auto",
        seeds=1, held_out=False, suite="security", adapters="", only=(), limit=0,
        network_policy="none", vision_judge="heuristic", synapse_iterations=1, vertex_ref="auto",
    )

    assert captured["judge_name"] == "claude"


def test_headless_live_generative_auto_uses_claude_judge(monkeypatch, tmp_path):
    captured = {}

    def run_generative_suite(**kwargs):
        captured.update(kwargs)
        return _Record()

    monkeypatch.setattr(cli, "run_generative_suite", run_generative_suite)
    monkeypatch.setattr(cli, "build_report", lambda _record, path: path.write_text("<html></html>"))
    monkeypatch.setattr(cli, "_print_generative_summary", lambda _record: None)

    cli._execute_track(
        "generative", run_id="x", out_dir=tmp_path, live=True, provider="codex", judge="auto",
        seeds=1, held_out=False, suite="security", adapters="", only=(), limit=0,
        network_policy="none", vision_judge="heuristic", synapse_iterations=1, vertex_ref="auto",
    )

    assert captured["judge_name"] == "claude"


def test_headless_live_repo_auto_uses_claude_judge(monkeypatch, tmp_path):
    captured = {}

    def run_repo_suite(**kwargs):
        captured.update(kwargs)
        return _Record()

    import gauntlet.repo as repo_pkg
    import gauntlet.repo.run as repo_run

    monkeypatch.setattr(repo_pkg, "run_repo_suite", run_repo_suite)
    monkeypatch.setattr(repo_run, "run_repo_suite", run_repo_suite)
    monkeypatch.setattr(cli, "build_report", lambda _record, path: path.write_text("<html></html>"))
    monkeypatch.setattr(cli, "_print_repo_summary", lambda _record: None)

    cli._execute_track(
        "repo", run_id="x", out_dir=tmp_path, live=True, provider="codex", judge="auto",
        seeds=1, held_out=False, suite="security", adapters="", only=(), limit=0,
        network_policy="none", vision_judge="heuristic", synapse_iterations=1, vertex_ref="auto",
    )

    assert captured["judge_name"] == "claude"
