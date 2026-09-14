"""Semantic Claude judges back live Quality, Generative, and Repo scoring."""

import gauntlet.generative.judge as gj
import gauntlet.quality.judge as qj
import gauntlet.repo.judge as rj
from gauntlet.analysis.models import CodeMetrics
from gauntlet.enums import Language
from gauntlet.generative.models import AppBrief, FeatureSpec
from gauntlet.quality.models import QualityTask, RequirementSpec
from gauntlet.repo.models import RepoTask


def test_quality_auto_live_builds_claude_semantic_judge(monkeypatch):
    monkeypatch.setattr(qj, "claude_json", lambda *_args, **_kwargs: {
        "architecture": 0.9, "readability": 0.8, "interface": 0.7, "rationale": "solid",
    })
    task = QualityTask(
        id="q", title="Q", language=Language.PYTHON, instruction="Implement add", scaffold="",
        requirements=[RequirementSpec("r", "add returns a sum", "goal", "math")],
    )
    metrics = CodeMetrics(
        loc=5, complexity=1, functions=1, duplication_pct=0.0, comment_ratio=0.0,
        has_tests=True, has_error_handling=True,
    )
    judge = qj.build_quality_judge("auto", live=True)
    score = judge.judge(metrics, 1.0, [], task=task, files={"solution.py": "def add(a,b): return a+b"})
    assert judge.model.startswith("claude-")
    assert score["architecture"] == 0.9 and score["interface"] == 0.7


def test_generative_auto_live_builds_claude_semantic_judge(monkeypatch):
    monkeypatch.setattr(gj, "claude_json", lambda *_args, **_kwargs: {
        "plan_score": 0.82, "rationale": "tracked and delivered",
    })
    brief = AppBrief(
        id="g", title="G", language=Language.PYTHON, stack="stdlib", instruction="Build a notes app",
        features=[FeatureSpec("create", "create", "api", "/api/notes")],
    )
    judge = gj.build_generative_judge("auto", live=True)
    score = judge.plan_score(
        brief, ["implement API"], 1.0, False, files={"app.py": "print('ok')"},
        checks=[{"id": "create", "passed": True, "detail": "201"}],
    )
    assert judge.model.startswith("claude-")
    assert score == 0.82


def test_repo_auto_live_builds_claude_semantic_judge(monkeypatch):
    monkeypatch.setattr(rj, "claude_json", lambda *_args, **_kwargs: {
        "semantic_patch_quality": 0.88, "rationale": "minimal fix",
    })
    task = RepoTask(
        id="r", title="R", problem_statement="Fix sum", files={"app.py": "def s(): return 0"},
        fix_files={"app.py": "def s(): return 1"}, hidden_test="",
    )
    judge = rj.build_repo_judge("auto", live=True)
    score = judge.patch_score(task, {"app.py": "def s(): return 1"}, task.fix_files, {"resolved": True})
    assert judge.model.startswith("claude-")
    assert score["semantic_patch_quality"] == 0.88


def test_offline_auto_stays_heuristic():
    assert qj.build_quality_judge("auto", live=False).model == "heuristic-quality-v0"
    assert gj.build_generative_judge("auto", live=False).model == "heuristic-generative-v0"
    assert rj.build_repo_judge("auto", live=False) is None
