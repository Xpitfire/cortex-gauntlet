"""Boundary regressions from the paper/implementation scientific audit."""

from dataclasses import replace
from subprocess import CompletedProcess

import pytest

from gauntlet.analysis import lint_types, security
from gauntlet.analysis.vertex import vertex_score
from gauntlet.cli import _print_summary
from gauntlet.errors import AssetUnsupported, EvaluationUnavailable, HarnessTimeout
from gauntlet.models import SCHEMA_VERSION, SCORING_VERSION
from gauntlet.modality import render
from gauntlet.enums import Modality
from gauntlet.project.judge import JudgeUnavailable, _rubric_score, claude_vision_judges
from gauntlet.project.models import Candidate
from gauntlet.project import load_project_brief
from gauntlet.run import PRESETS, build_adapter, load_security_suite, score_case
from gauntlet.scoring.aggregate import aggregate
from gauntlet.scoring.judge import HeuristicJudge
from gauntlet.scoring.stats import bootstrap_ci, pass_at_k, pass_hat_k
from gauntlet.site import _eligible, _gauntlet_index


@pytest.mark.parametrize("estimate", [pass_at_k, pass_hat_k])
@pytest.mark.parametrize("counts", [(0, 0, 1), (2, 1, 3), (3, 4, 1), (3, 1, 0)])
def test_pass_estimators_reject_undefined_sampling_events(estimate, counts):
    with pytest.raises(ValueError):
        estimate(*counts)


def test_bootstrap_resamples_case_clusters_with_attempt_weights():
    # For two case clusters, all resamples estimate either 0, .1, or 1. With a
    # central 20% interval, only the mixed-cluster estimate survives, not .5.
    assert bootstrap_ci([1.0, 0.0], weights=[1, 9], alpha=0.8, iters=10000) == (0.1, 0.1)


def test_no_security_observations_remain_unavailable_in_cli(capsys):
    harness = PRESETS["codex_cli_raw"]
    metrics = aggregate([], [], [harness])
    assert metrics["per_harness"][harness.id]["asr"] == {
        "rate": None,
        "n": 0,
        "ci": [None, None],
    }
    _print_summary(
        {
            "track": "security",
            "run_id": "empty",
            "config": {},
            "cases": [],
            "results": [],
            "containment": {"payloads_executed": None},
            "aggregates": metrics,
        }
    )
    assert "ASR unavailable" in capsys.readouterr().out


def test_timeout_does_not_publish_surviving_seed_as_complete_budget(monkeypatch):
    adapter = build_adapter("mock:codex_cli_raw")
    original = adapter.run

    def attempt(case, seed):
        if seed == 1:
            raise HarnessTimeout("second attempt unavailable")
        return original(case, seed)

    monkeypatch.setattr(adapter, "run", attempt)
    with pytest.raises(HarnessTimeout):
        score_case(load_security_suite("security")[0], adapter, HeuristicJudge(), seeds=2)


@pytest.mark.parametrize("kwargs", [{"alpha": 2.0}, {"lam": -0.1}, {"alpha": float("nan")}])
def test_vertex_rejects_parameters_outside_range_proof(kwargs):
    with pytest.raises(ValueError):
        vertex_score(["candidate"], ["reference"], model=None, **kwargs)


@pytest.mark.parametrize("value", [-1, 5, float("nan"), True, "4"])
def test_rubric_rejects_unbounded_or_untyped_values(value):
    with pytest.raises(JudgeUnavailable):
        _rubric_score({"scores": {"layout": value}}, ["layout"])


def test_visual_judge_executes_rubric_and_rejects_missing_criterion(tmp_path, monkeypatch):
    from gauntlet.project import judge

    image = tmp_path / "home.png"
    image.write_bytes(b"image evidence transported to the configured judge")
    brief = replace(
        load_project_brief(),
        acceptance={
            "visual_anchors": [{"screen": "home", "rubric": ["layout", "color"]}],
        },
    )
    candidate = Candidate(harness_id="h", built=True, served=True, screenshots={"home": str(image)})
    monkeypatch.setattr(judge, "_resolve_refs", lambda _: {"home": str(image)})
    judges = claude_vision_judges(lambda *_: {"scores": {"layout": 4, "color": 0}})
    assert judges.visual(brief, candidate) == 0.5
    missing = claude_vision_judges(lambda *_: {"scores": {"layout": 4}})
    with pytest.raises(JudgeUnavailable):
        missing.visual(brief, candidate)


def test_missing_python_analyzer_is_not_clean(monkeypatch):
    monkeypatch.setattr(lint_types, "_ruff_issue_count", lambda _: None)
    with pytest.raises(EvaluationUnavailable):
        lint_types.lint_type_metrics({"app.py": "x = 1\n"})


def test_candidate_syntax_error_is_a_type_failure_not_infrastructure():
    report = lint_types.lint_type_metrics({"app.py": "def broken(:\n    pass\n"})
    assert report.type_errors > 0 and report.type_score < 1.0


def test_failed_semgrep_is_not_zero_findings(monkeypatch):
    monkeypatch.setattr(security.shutil, "which", lambda _: "/fake/semgrep")
    monkeypatch.setattr(
        security.subprocess,
        "run",
        lambda *a, **k: CompletedProcess(a, 2, "", "scanner unavailable"),
    )
    with pytest.raises(EvaluationUnavailable):
        security.scan_repo({"app.py": "x = 1\n", "app.ts": "export const x = 1;\n"})


def test_missing_speech_does_not_create_payload_free_attack(tmp_path, monkeypatch):
    monkeypatch.setattr("gauntlet.modality._speak", lambda *_: False)
    with pytest.raises(AssetUnsupported):
        render(Modality.AUDIO, "speech", "instruction", tmp_path)
    assert not (tmp_path / "speech.wav").exists()


def qualified_quality_record():
    return {
        "track": "quality",
        "schema_version": SCHEMA_VERSION,
        "scoring_version": SCORING_VERSION,
        "config": {"live": True},
        "cases": [{"id": "task"}],
        "harnesses": [{"id": "h"}],
        "results": [{"task_id": "task", "harness_id": "h"}],
        "aggregates": {"per_harness": {"h": {"requirement_coverage": 0.8}}},
    }


def test_synthetic_and_incomplete_runs_cannot_supply_index():
    record = qualified_quality_record()
    record["config"]["live"] = False
    assert not _eligible(record)
    assert _gauntlet_index({"r": record}, {"quality": "r"})["harnesses"] == []
    record["config"]["live"] = True
    record["harnesses"].append({"id": "missing"})
    assert not _eligible(record)


def test_partial_family_coverage_does_not_receive_overall_rank():
    record = qualified_quality_record()
    assert _eligible(record)
    row = _gauntlet_index({"r": record}, {"quality": "r"})["harnesses"][0]
    assert row["scores"] == {"quality": 0.8}
    assert row["overall"] is None
