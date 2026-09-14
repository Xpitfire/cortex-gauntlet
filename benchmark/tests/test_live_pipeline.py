"""The live code-gen pipeline (capture → score), verifiable offline.

The bug this guards against: a live `--track quality --live --provider codex,cortex` run scored every
Cortex cell as "0/2 ✗" because the generated `solution.py` was never captured — the `cortex agent ask`
reply was parsed against the wrong shape and a runtime/provider failure was swallowed as a silent FAIL.

We can't drive the real CLIs here (auth + tokens), so we exercise the exact capture/score path with
stub binaries that emit the *real* CLI output shapes, as a ladder:

  1. parse    — the FILE-block + reply parsers against the formats the real CLIs actually produce
  2. mock     — score_task with no live harness (the offline corpus path) still runs + scores
  3. subset   — fake codex (writes a file) and fake cortex (echoes the reply) flow end-to-end to a PASS
  4. failure  — a failed cortex task surfaces as an ERROR cell with the reason, not a misleading 0/N FAIL
"""

import stat
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import gauntlet.livegen.base as base
from gauntlet.bootstrap import app_files, template_available
from gauntlet.enums import Language
from gauntlet.livegen.adapters import CodexCodeGen, CortexCodeGen, _cortex_reply, _parse_files
from gauntlet.livegen.models import CodeGenRequest
from gauntlet.quality.corpus import load_quality_tasks
from gauntlet.quality.judge import HeuristicQualityJudge
from gauntlet.quality.models import QualityTask, RequirementSpec
from gauntlet.quality.score import score_task
from gauntlet.run import PRESETS
from gauntlet.synapse import SynapsePlanner

# the exact reply a successful `cortex agent ask` prints: two status lines then the task-log JSON
# envelope, whose payload text puts a BLANK LINE between `FILE:` and the fenced block (the real shape).
_ADD = "def add(a, b):\n    return a + b\n"
_REPLY_TEXT = "FILE: solution.py\n\n```python\n" + _ADD + "```"
_CORTEX_OK = (
    'task-1 running\ntask-1 succeeded\n'
    '{"status":"ok","summary":"completed","result":{"payloads":[{"text":'
    + __import__("json").dumps(_REPLY_TEXT) + ',"mediaUrl":null}]}}'
)
_CORTEX_FAIL = (
    "task-2 running\ntask-2 failed\n"
    'GatewayClientRequestError: Auth profile "openai:default" uses oauth auth, but '
    "openai/openai-responses requires an OpenAI API key profile."
)


def _add_task() -> QualityTask:
    test = "from solution import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    return QualityTask(
        id="add", title="Add", language=Language.PYTHON,
        instruction="Implement add(a, b) returning a + b.", scaffold="",
        requirements=[RequirementSpec(
            id="r-add", text="add(a, b) returns a + b", kind="deliverable", category="tests",
            good_code=_ADD, evidence="def add", test=test,
        )],
    )


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _enable_stub_synapse_loop(monkeypatch):
    monkeypatch.setattr("gauntlet.synapse.synapse_available", lambda: True)
    module = types.ModuleType("gauntlet.synapse_loop")

    def _synapse_codegen(codegen, _task, prompt, main_file, language, timeout_s, **_kwargs):
        result = codegen.generate(
            CodeGenRequest(
                prompt=prompt, language=language, main_file=main_file, timeout_s=timeout_s,
                scaffold=True, scaffold_governance_only=True,
            )
        )
        files = dict(result.files) if result.files else (
            {main_file: result.main_code} if (result.main_code or "").strip() else {}
        )
        files = app_files(files)
        return files, SimpleNamespace(iterations=1), (result.error if not files else "")

    module.synapse_codegen = _synapse_codegen
    monkeypatch.setitem(sys.modules, "gauntlet.synapse_loop", module)


# ── 1. parse — the parsers handle the formats the real CLIs actually produce ──────────────────────
def test_fileblock_tolerates_blank_line_before_fence():
    # the agent emits `FILE: path\n\n```...` — a blank line the old regex rejected, dropping the file
    files = _parse_files(_REPLY_TEXT)
    assert files == {"solution.py": _ADD}
    multi = "FILE: a.py\n\n```python\nA = 1\n```\nFILE: b.py\n```python\nB = 2\n```"
    assert set(_parse_files(multi)) == {"a.py", "b.py"}  # both files captured, blank line or not


def test_cortex_reply_extracts_payload_and_surfaces_failure():
    reply, err = _cortex_reply(_CORTEX_OK)
    assert err == "" and reply == _REPLY_TEXT  # success: payload text, no error
    reply, err = _cortex_reply(_CORTEX_FAIL)
    assert reply == "" and "OpenAI API key" in err  # failure: empty reply, reason surfaced (not swallowed)


# ── 2. mock — the offline corpus path scores without any live harness ──────────────────────────────
def test_mock_run_scores_offline():
    task = next(t for t in load_quality_tasks() if t.language is Language.PYTHON)
    r = score_task(task, PRESETS["cortex_wrapped"], SynapsePlanner(), HeuristicQualityJudge())
    assert r.dynamic_ran and not r.gen_error and r.code.strip()


# ── 3. subset — fake codex / fake cortex flow end-to-end to a captured, passing solution ───────────
def test_live_subset_captures_and_passes(tmp_path, monkeypatch):
    if not template_available():
        pytest.skip("authorized Cortex project template is not installed")
    _enable_stub_synapse_loop(monkeypatch)
    codex = _stub(tmp_path / "codex", (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "ws = a[a.index('--cd') + 1] if '--cd' in a else '.'\n"
        f"pathlib.Path(ws, 'solution.py').write_text({_ADD!r})\n"
    ))
    cortex = _stub(tmp_path / "cortex", "print(%r)\n" % _CORTEX_OK)
    which = {"codex": str(codex), "cortex": str(cortex)}
    real_which = base.shutil.which
    monkeypatch.setattr(base.shutil, "which", lambda n: which.get(n) or real_which(n))
    task = _add_task()

    # raw codex arm: writes the file in the workspace; cortex arm: echoes it through the Synapse loop
    raw = score_task(task, PRESETS["codex_cli_raw"], SynapsePlanner(), HeuristicQualityJudge(),
                     CodexCodeGen(PRESETS["codex_cli_raw"]))
    gov = score_task(task, PRESETS["cortex_wrapped"], SynapsePlanner(), HeuristicQualityJudge(),
                     CortexCodeGen(PRESETS["cortex_wrapped"], provider="codex"))
    for r in (raw, gov):
        assert "solution.py" in r.files and not r.gen_error
        assert r.dynamic_ran and r.functional_passed == r.functional_total == 1


# ── 3b. the Cortex arm wraps the LOCAL base CLI through the Synapse loop (no remote runtime) ───────
def test_cortex_arm_runs_local_cli_through_synapse_loop(tmp_path, monkeypatch):
    if not template_available():
        pytest.skip("authorized Cortex project template is not installed")
    _enable_stub_synapse_loop(monkeypatch)
    from gauntlet.livegen import build_codegen
    codex = _stub(tmp_path / "codex", (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "ws = a[a.index('--cd') + 1] if '--cd' in a else '.'\n"
        f"pathlib.Path(ws, 'solution.py').write_text({_ADD!r})\n"
    ))
    real_which = base.shutil.which
    monkeypatch.setattr(base.shutil, "which", lambda n: str(codex) if n == "codex" else real_which(n))
    # build_codegen("cortex") now returns the local codex adapter; score_task drives it via Synapse
    gov = build_codegen("cortex", PRESETS["cortex_wrapped"])
    r = score_task(_add_task(), PRESETS["cortex_wrapped"], SynapsePlanner(), HeuristicQualityJudge(), gov)
    assert "solution.py" in r.files and not r.gen_error
    assert r.dynamic_ran and r.functional_passed == r.functional_total == 1


# ── 4. failure — a failed cortex task is an ERROR cell with the reason, not a silent 0/N FAIL ──────
def test_live_failure_surfaces_as_error(tmp_path, monkeypatch):
    if not template_available():
        pytest.skip("authorized Cortex project template is not installed")
    _enable_stub_synapse_loop(monkeypatch)
    cortex = _stub(tmp_path / "cortex", "print(%r)\n" % _CORTEX_FAIL)
    real_which = base.shutil.which
    monkeypatch.setattr(base.shutil, "which", lambda n: str(cortex) if n == "cortex" else real_which(n))

    # the adapter reports the failure, not empty code
    res = CortexCodeGen(PRESETS["cortex_wrapped"], provider="codex").generate(
        CodeGenRequest(prompt="p", language="python", main_file="solution.py", timeout_s=5))
    assert not res.ok and "OpenAI API key" in res.error

    # score_task carries the reason as gen_error; the TUI cell turns that into an ERROR (not a FAIL)
    r = score_task(_add_task(), PRESETS["cortex_wrapped"], SynapsePlanner(), HeuristicQualityJudge(),
                   CortexCodeGen(PRESETS["cortex_wrapped"], provider="codex"))
    assert r.gen_error and "OpenAI API key" in r.gen_error

    import dataclasses

    from gauntlet.tui.bridge import _load_quality
    from gauntlet.tui.events import CellStatus
    cell = _load_quality(dataclasses.asdict(r), {}, {})
    assert cell.status is CellStatus.ERROR
