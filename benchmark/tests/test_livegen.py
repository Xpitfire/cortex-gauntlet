"""Phase 1 live code-gen: adapter dispatch + the live pipeline (real analysis) via a Fake adapter."""

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from gauntlet.bootstrap import template_available
from gauntlet.errors import HarnessSetupError
from gauntlet.livegen import CodeGenRequest, FakeCodeGen, build_codegen
from gauntlet.livegen.adapters import ClaudeCodeGen, CodexCodeGen, CortexCodeGen
from gauntlet.quality.corpus import load_quality_tasks
from gauntlet.quality.judge import HeuristicQualityJudge
from gauntlet.quality.sast import scan_code
from gauntlet.quality.score import _live_prompt, score_task
from gauntlet.run import PRESETS
from gauntlet.synapse import SynapsePlanner


def _task(tid):
    return next(t for t in load_quality_tasks() if t.id == tid)


def _assemble(task, attr):
    return task.scaffold + "\n" + "\n".join(getattr(r, attr) for r in task.requirements)


def test_build_codegen_dispatch():
    m = PRESETS["codex_cli_raw"]
    assert isinstance(build_codegen("codex", m), CodexCodeGen)
    assert isinstance(build_codegen("claude", m), ClaudeCodeGen)
    # the "cortex" arm wraps the SAME local base CLI (the Synapse loop drives it), so it dispatches to
    # the base adapter; the remote Cortex runtime is the opt-in "cortex-runtime" path.
    assert isinstance(build_codegen("cortex", m), CodexCodeGen)
    assert isinstance(build_codegen("cortex:claude", m), ClaudeCodeGen)
    assert isinstance(build_codegen("cortex-runtime:claude", m), CortexCodeGen)
    with pytest.raises(ValueError):
        build_codegen("bogus", m)


def test_codex_codegen_ignores_user_config():
    argv = CodexCodeGen(PRESETS["codex_cli_raw"], model="gpt-5.5", effort="xhigh").build_argv(
        "codex", "prompt", Path("/tmp/ws"), "main.py")
    assert "--ignore-user-config" in argv
    assert "--json" in argv


def test_codex_codegen_allows_extracted_scaffold_task_writes(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / ".agents" / "tasks").mkdir(parents=True)
    (workspace / ".codex").mkdir()
    argv = CodexCodeGen(PRESETS["cortex_wrapped"]).build_argv("codex", "prompt", workspace, "main.py")
    writable = [argv[idx + 1] for idx, arg in enumerate(argv) if arg == "--add-dir"]
    assert str(workspace / ".agents") in writable
    assert str(workspace / ".agents" / "tasks") in writable
    assert str(workspace / ".codex") in writable


def test_live_prompt_includes_signatures_and_constraints():
    prompt = _live_prompt(_task("data_access"))
    assert "def find_user(conn, name)" in prompt
    assert "solution.py" in prompt and "standard library" in prompt


def test_fake_adapter_returns_requested_code():
    result = FakeCodeGen(PRESETS["cortex_wrapped"], "x = 1\n").generate(CodeGenRequest(prompt="p"))
    assert result.ok and result.main_code == "x = 1\n" and result.backend == "cortex_wrapped"


def test_live_pipeline_runs_real_analysis_on_good_code():
    task = _task("password_utils")
    fake = FakeCodeGen(PRESETS["codex_cli_raw"], _assemble(task, "good_code"))
    r = score_task(task, PRESETS["codex_cli_raw"], SynapsePlanner(), HeuristicQualityJudge(), codegen=fake)
    assert r.synapse_backend.startswith("live:")
    assert r.dynamic_ran and r.functional_total >= 1
    assert r.functional_passed == r.functional_total  # reference good code passes the hidden tests
    assert all(f.severity.value != "high" for f in r.findings)  # and is Bandit-clean


def test_quality_cortex_requires_synapse_for_live_codegen(monkeypatch):
    monkeypatch.setattr("gauntlet.synapse.synapse_available", lambda: False)
    task = _task("password_utils")
    fake = FakeCodeGen(PRESETS["cortex_wrapped"], _assemble(task, "good_code"))
    with pytest.raises(HarnessSetupError, match="Synapse"):
        score_task(task, PRESETS["cortex_wrapped"], SynapsePlanner(), HeuristicQualityJudge(), fake)


def test_quality_cortex_synapse_requests_governance_scaffold(monkeypatch):
    if not template_available():
        pytest.skip("project template archive not present")
    monkeypatch.setattr("gauntlet.synapse.synapse_available", lambda: True)
    task = _task("password_utils")
    calls = {}
    module = types.ModuleType("gauntlet.synapse_loop")

    def _synapse_codegen(*_args, scaffold=False, **_kwargs):
        calls["scaffold"] = scaffold
        return {"solution.py": _assemble(task, "good_code")}, SimpleNamespace(iterations=1), ""

    module.synapse_codegen = _synapse_codegen
    monkeypatch.setitem(sys.modules, "gauntlet.synapse_loop", module)
    codegen = FakeCodeGen(PRESETS["cortex_wrapped"], _assemble(task, "good_code"))
    r = score_task(task, PRESETS["cortex_wrapped"], SynapsePlanner(), HeuristicQualityJudge(), codegen)
    assert calls["scaffold"] is True
    assert r.dynamic_ran and r.functional_passed == r.functional_total


def test_live_pipeline_catches_bad_code():
    task = _task("data_access")
    bad_code = _assemble(task, "bad_code")
    fake = FakeCodeGen(PRESETS["codex_cli_raw"], bad_code)
    r = score_task(task, PRESETS["codex_cli_raw"], SynapsePlanner(), HeuristicQualityJudge(), codegen=fake)
    # The vibe-coded concatenated SQL fails the injection test; the deterministic offline SAST rule carries
    # the CWE mapping even when optional Bandit/Semgrep binaries are not installed locally.
    assert r.functional_passed < r.functional_total
    assert any(f.cwe == "CWE-89" for f in scan_code(bad_code))
