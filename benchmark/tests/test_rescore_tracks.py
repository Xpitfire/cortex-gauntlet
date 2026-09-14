"""Re-score from persisted artifacts (any track) — no harness re-generation, the configured judges DO
run. Covers the project reconstruct-from-sandbox path and the ReplayCodegen used by quality/repo."""

import json
from pathlib import Path

from gauntlet.rescore_tracks import ReplayCodegen, _persisted_cells, rescore_project


def test_replay_codegen_returns_persisted_files_not_a_generation():
    r = ReplayCodegen({"a.py": "x = 1\n"}).generate(None)
    assert r.files == {"a.py": "x = 1\n"} and r.ok and r.backend == "replay"
    assert ReplayCodegen({}).generate(None).ok is False  # nothing persisted → not ok


def test_project_rescore_from_persisted_sandbox_no_docker(tmp_path):
    # synthesize a finished project run: one arm with a repo + the captured probe observation
    run_dir = tmp_path / "tui-project-T"
    arm = run_dir / "sandbox" / "codex_cli_raw"
    (arm / "repo" / "src").mkdir(parents=True)
    (arm / "repo" / "package.json").write_text('{"scripts": {"start": "node src/server.ts"}}')
    (arm / "repo" / "src" / "server.ts").write_text(
        "// backend API server with routes for cart and checkout\nexport const products = [];\n")
    (arm / "result.json").write_text(json.dumps({
        "served": True,
        "ui": {"journeys": [{"id": "home", "passed": True}, {"id": "cart", "passed": True},
                            {"id": "checkout_payment", "passed": False}]},
        "robustness": [{"id": "empty_cart", "passed": True}],
        "pwa_a11y": [{"id": "manifest", "passed": True}]}))

    out = rescore_project(run_dir, vision_judge="heuristic")  # heuristic = no model load, fast
    assert out["rescored"] == 1
    assert (Path(out["out_dir"]) / "report.html").exists()
    rec = json.loads((Path(out["out_dir"]) / "runrecord.json").read_text())
    s = rec["aggregates"]["per_harness"]["codex_cli_raw"]
    assert s["build"] == 1 and s["functional"] > 0          # the persisted journeys were re-scored
    assert s["vertex"] >= 0.0                                 # VERTEX computed (no swap, no crash)


def test_generative_rescore_reuses_execution_recomputes_static(tmp_path):
    # a finished generative run: the feature/build observation must be REUSED, only lint/security recomputed
    run_dir = tmp_path / "tui-generative-T"
    run_dir.mkdir()
    result = {"brief_id": "chat_app", "harness_id": "codex_cli_raw", "language": "python", "n_seeds": 1,
              "feature_count": 2, "build_pass": 1, "feature_pass_counts": [1, 0],
              "feature_claim_counts": [1, 1], "seed_completeness": [0.5], "feature_rate": [1.0, 0.0],
              "plan_score": 0.8, "visual_score": 0.7, "honesty": 0.9, "guardrail_score": None,
              "milestones": ["m1 (2)"], "rep_features": [{"feature_id": "f1", "name": "f1", "passed": True,
              "claimed": True}], "screenshot": None, "synapse_backend": "shim",
              "files": {"app.py": "import os\nx=1\n"}, "lint_issues": 0, "type_errors": 0,
              "code_quality": 1.0, "security": 1.0, "findings": 0, "security_tool": "",
              "robustness": 1.0, "held_out_passed": 0, "held_out_total": 0}
    (run_dir / "runrecord.json").write_text(json.dumps({"track": "generative", "results": [result],
                                                        "config": {"seeds": 1}}))
    from gauntlet.rescore_tracks import rescore_generative
    out = rescore_generative(run_dir)
    assert out["rescored"] == 1
    rec = json.loads((Path(out["out_dir"]) / "runrecord.json").read_text())
    r = rec["results"][0]
    assert r["feature_pass_counts"] == [1, 0] and r["build_pass"] == 1   # execution observation REUSED
    assert "code_quality" in r and "security" in r                       # static signals present (recomputed)


def test_persisted_cells_prefers_checkpoint_then_runrecord(tmp_path):
    run_dir = tmp_path / "tui-repo-T"
    run_dir.mkdir()
    (run_dir / "runrecord.json").write_text(json.dumps({"results": [
        {"task_id": "bug1", "harness_id": "codex_cli_raw", "files": {"fix.py": "def f(): return 1\n"}}]}))
    cells = _persisted_cells(run_dir)                         # no checkpoint → falls back to the runrecord
    assert cells == {("bug1", "codex_cli_raw"): {"fix.py": "def f(): return 1\n"}}
