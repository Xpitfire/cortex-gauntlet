"""Track P judge provenance: backends are an explicit choice (never a silent fallback), the recorded
sandbox + judge backends reflect what actually ran, and an unavailable real judge raises (no fake 0s)."""

import pytest

import gauntlet.project.judge as judge
from gauntlet.project import load_project_brief, run_project_suite
from gauntlet.project.judge import JudgeUnavailable, build_project_judges, clip_judges, heuristic_judges
from gauntlet.project.models import Candidate
from gauntlet.project.score import score_project


def test_heuristic_backend_is_explicit_and_labeled():
    assert build_project_judges("heuristic", live=False).backend == "heuristic-proxy"


def test_vision_judges_require_live():
    with pytest.raises(JudgeUnavailable):
        build_project_judges("clip", live=False)  # mock has no real renders
    with pytest.raises(JudgeUnavailable):
        build_project_judges("claude-vision", live=False)


def test_claude_vision_raises_when_cli_absent(monkeypatch):
    monkeypatch.setattr(judge.shutil, "which", lambda _name: None)  # no `claude` on PATH
    with pytest.raises(JudgeUnavailable):
        build_project_judges("claude-vision", live=True)  # never silently downgrades to heuristic


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError):
        build_project_judges("gpt-vision", live=True)


def test_sandbox_backend_is_independent_of_judge_backend():
    brief = load_project_brief()
    cand = Candidate(harness_id="x", built=True, served=True,
                     files={"server/api.ts": "x", "ui/app.tsx": "y"},
                     journey_pass={"home": True}, module_descriptors=["http api"])
    r = score_project(brief, cand, heuristic_judges(), sandbox_backend="docker")
    assert r.sandbox_backend == "docker"  # reflects execution, NOT inferred from the judge
    assert r.signals.detail["judge_backend"] == "heuristic-proxy"


def test_clip_visual_uses_image_cosine(monkeypatch, tmp_path):
    """The CLIP judge measures real image-image cosine (here with stubbed embeddings — no torch needed)."""

    import base64

    brief = load_project_brief()
    # Authored one-pixel PNGs: no licensed storefront screenshots are required.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1cAAAAASUVORK5CYII=")
    monkeypatch.setattr("gauntlet.project.corpus.fixture_dir", lambda: tmp_path)
    shots = {}
    for anchor in brief.acceptance["visual_anchors"]:
        path = tmp_path / anchor["ref"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        shots[anchor["screen"]] = str(path)
    cand = Candidate(harness_id="x", built=True, served=True, screenshots=shots,
                     files={"ui/a.tsx": "x"}, module_descriptors=["react ui"])
    monkeypatch.setattr(judge, "embed_images", lambda paths, model: ([[1.0, 0.0] for _ in paths], "clip:test"))
    j = clip_judges("clip-test")
    assert j.visual(brief, cand) == 1.0  # identical unit vectors → cosine 1 across screens


def test_missing_reference_images_are_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr("gauntlet.project.corpus.fixture_dir", lambda: tmp_path)
    brief = load_project_brief()
    candidate = Candidate(harness_id="x", built=True, served=True)
    with pytest.raises(JudgeUnavailable):
        clip_judges().visual(brief, candidate)


def test_mock_record_is_labeled_mock_and_heuristic():
    rec = run_project_suite().to_dict()  # full set so the raw-vs-cortex delta is populated
    assert rec["config"]["judge"] == "heuristic-proxy"  # the backend that actually ran
    assert rec["config"]["vertex_ref"] == "authored"  # auto keeps offline fixtures deterministic
    assert rec["config"]["basis"].startswith("mock")  # not presented as measured
    assert rec["aggregates"]["synapse_delta"]["basis"].startswith("mock")  # delta flagged modelled
    assert all(r["sandbox_backend"] == "mock" for r in rec["results"])
