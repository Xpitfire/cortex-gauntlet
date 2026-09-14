"""Tests for Track P (project) — brief load, mock candidate, composite scoring, gating, aggregate."""

from gauntlet.project import load_project_brief, run_project_suite, score_project
from gauntlet.project.run import DEFAULT_PROJECT_HARNESSES
from gauntlet.project.judge import Judges
from gauntlet.project.models import Candidate
from gauntlet.project.mock import mock_candidate
from gauntlet.run import PRESETS


def _scaffold_key(suffix: str = "") -> str:
    import pytest
    from gauntlet.bootstrap import scaffold_paths, template_available

    if not template_available():
        pytest.skip("project template archive not present")
    return next(p for p in scaffold_paths() if not suffix or p.endswith(suffix))


def test_missing_judge_signal_is_unavailable_not_a_reweighted_score():
    import pytest
    from gauntlet.errors import EvaluationUnavailable

    brief = load_project_brief()
    cand = Candidate(harness_id="t", built=True, served=True, capabilities=["browse", "cart"],
                     journey_pass={"home": True, "cart": True},
                     files={"src/server.ts": "//", "public/i.html": ""})

    def _race(*_a):
        raise ValueError("bad value(s) in fds_to_keep")

    judges = Judges(visual=lambda *_: 0.8, code_arch=_race, ux=lambda *_: 0.7, backend="test")
    with pytest.raises(EvaluationUnavailable, match="code_arch"):
        score_project(brief, cand, judges, sandbox_backend="docker")

    def _bug(*_a):
        raise RuntimeError("a genuine judge bug")

    with pytest.raises(RuntimeError):                               # a NON-race judge error still propagates
        score_project(brief, cand, Judges(visual=lambda *_: 0.8, code_arch=_bug, ux=lambda *_: 0.7,
                                          backend="test"), sandbox_backend="docker")


def test_mock_suite_runs_all_harnesses_and_serializes():
    rec = run_project_suite()
    assert len(rec.results) == len(DEFAULT_PROJECT_HARNESSES)  # one result per default harness
    assert rec.to_json()  # RunRecord serializes
    assert set(rec.aggregates["per_harness"]) == {h.id for h in rec.harnesses}


def test_build_gate_zeros_everything():
    brief = load_project_brief()
    dead = Candidate(harness_id="x", built=False, served=False, files={"a.py": "def f(): pass"})
    result = score_project(brief, dead)
    s = result.signals
    assert s.build == 0 and s.composite == 0.0 and s.functional == 0.0 and s.visual == 0.0


def test_judges_gated_on_serving():
    brief = load_project_brief()
    built_not_served = Candidate(harness_id="x", built=True, served=False,
                                 files={"ui/a.tsx": "x", "server/b.ts": "y"})
    s = score_project(brief, built_not_served).signals
    assert s.build == 1
    assert s.visual == 0.0 and s.ux == 0.0  # vision/ux need a served app
    assert s.code_arch > 0.0  # static repo judge still runs


def test_scaffold_only_candidate_gets_no_app_score():
    brief = load_project_brief()
    scaffold = _scaffold_key(".py")
    cand = Candidate(
        harness_id="x", built=True, served=True, capabilities=["complete checkout"],
        journey_pass={"home": True, "cart": True}, pwa_a11y={"manifest": True},
        robustness={"unknown_route": True},
        files={scaffold: "cart checkout stripe products AKIA_FAKE_TEMPLATE_SECRET"},
    )

    result = score_project(brief, cand)
    s = result.signals

    assert s.functional == s.pwa_a11y == s.robustness == 0.0
    assert s.vertex == s.visual == s.code_arch == s.ux == s.composite == 0.0
    assert s.code_health == 0.0 and s.security == 0.0
    assert result.capabilities == [] and result.module_descriptors == []
    assert s.detail["score_file_count"] == 0 and s.detail["excluded_setup_file_count"] == 1


def test_project_static_signals_ignore_scaffold_files():
    brief = load_project_brief()
    scaffold = _scaffold_key(".py")
    cand = Candidate(
        harness_id="x", built=True, served=False,
        files={
            scaffold: "AKIA_FAKE_TEMPLATE_SECRET = 'should not count'",
            "src/server/api.ts": "export const listProducts = () => []\n",
            "tests/api.test.ts": "import '../src/server/api'\n",
        },
    )

    result = score_project(brief, cand)

    assert result.signals.detail["score_file_count"] == 2
    assert result.signals.detail["excluded_setup_file_count"] == 1
    assert result.signals.code_health >= 0.8
    assert result.signals.security >= 0.9
    assert all("AKIA" not in item for item in result.module_descriptors)


def test_synapse_beats_raw_on_long_horizon():
    brief = load_project_brief()
    raw = score_project(brief, mock_candidate(brief, PRESETS["codex_cli_raw"])).signals
    cortex = score_project(brief, mock_candidate(brief, PRESETS["cortex_wrapped"])).signals
    assert cortex.composite > raw.composite
    assert cortex.functional >= raw.functional
    assert cortex.vertex >= raw.vertex


def test_signal_vector_bounded():
    brief = load_project_brief()
    s = score_project(brief, mock_candidate(brief, PRESETS["cortex_claude"])).signals
    for v in (s.functional, s.pwa_a11y, s.code_health, s.robustness, s.security, s.vertex, s.visual,
              s.code_arch, s.ux, s.composite):
        assert 0.0 <= v <= 1.0
