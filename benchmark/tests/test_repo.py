"""Track R (repository issue-resolution, SWE-bench style), verifiable offline.

A correct patch makes a hidden test that fails on the buggy base repo pass. We check the corpus is a
clean fail→pass oracle, the mock models a governed-arm advantage, and the live pipeline (capture the
arm's edited files → overlay on the base repo → run the hidden test) resolves with a stub harness and
surfaces an ERROR — not a silent unresolved — when the harness produces no patch.
"""

import json
import stat
from pathlib import Path

import gauntlet.livegen.base as base
import pytest
from gauntlet.bootstrap import template_available
from gauntlet.livegen.adapters import CodexCodeGen, CortexCodeGen
from gauntlet.livegen.models import CodeGenResult
from gauntlet.repo.corpus import load_repo_tasks
from gauntlet.repo.run import DEFAULT_REPO_HARNESSES, run_repo_suite
from gauntlet.repo.score import score_repo_task
from gauntlet.run import PRESETS


def test_corpus_tasks_are_fail_then_pass_oracles():
    from gauntlet.analysis.dynamic import run_python_tests_files
    for t in load_repo_tasks():
        base_run = run_python_tests_files(dict(t.files), t.hidden_test)
        fixed = run_python_tests_files({**t.files, **t.fix_files}, t.hidden_test)
        assert base_run.total > 0 and base_run.passed < base_run.total  # the bug is caught
        assert fixed.passed == fixed.total > 0                          # the reference fix resolves it


def test_mock_suite_resolves_and_governed_leads():
    rec = run_repo_suite()
    d = rec.to_dict()
    assert json.dumps(d) and d["track"] == "repo"  # a proper, serializable RunRecord
    ph = d["aggregates"]["per_harness"]
    # derive from the track's own default roster: a hardcoded list silently goes stale whenever a
    # harness is added, and this assertion is about "every default harness reported", not a fixed set
    assert set(ph) == set(DEFAULT_REPO_HARNESSES)
    delta = d["aggregates"]["synapse_delta"]["resolution_rate"]
    assert delta["cortex_wrapped"] >= delta["raw"]  # governance tracks the issue to a validated fix


def test_suite_record_renders_a_report_and_joins_the_site(tmp_path):
    from gauntlet.report import build_report
    rec = run_repo_suite(limit=2)
    html = build_report(json.loads(rec.to_json()), tmp_path / "report.html")
    # "Bugfix" is the display name for Track R (stable id stays "repo"); page notes the SWE-bench basis
    assert "Bugfix" in html and "SWE-bench" in html and rec.run_id in html


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class _RecordingCodeGen:
    def __init__(self, files):
        self.files = files
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return CodeGenResult("recording", "", files=self.files, ok=True)


def test_governed_repo_live_request_seeds_scaffold_and_filters_it():
    if not template_available():
        pytest.skip("project template archive not present")
    task = next(t for t in load_repo_tasks() if t.id == "sum-evens")
    path = task.edit_paths[0]
    codegen = _RecordingCodeGen({path: task.fix_files[path], "AGENTS.md": "scaffold\n"})
    result = score_repo_task(task, PRESETS["cortex_wrapped"], codegen)
    assert codegen.requests and codegen.requests[0].scaffold
    assert codegen.requests[0].scaffold_governance_only
    assert result.resolved and "AGENTS.md" not in result.files


def test_live_pipeline_applies_patch_and_resolves(tmp_path, monkeypatch):
    task = next(t for t in load_repo_tasks() if t.id == "sum-evens")
    path, fix = task.edit_paths[0], task.fix_files[task.edit_paths[0]]

    # fake cortex echoes the fix as a FILE: block (with the blank line the real CLI emits)
    reply = f"FILE: {path}\n\n```python\n{fix}```"
    envelope = ('task-1 running\ntask-1 succeeded\n'
                '{"status":"ok","result":{"payloads":[{"text":' + json.dumps(reply) + '}]}}')
    cortex = _stub(tmp_path / "cortex", "print(%r)\n" % envelope)
    # fake codex writes the fixed file (nested path) into the --cd workspace
    codex = _stub(tmp_path / "codex", (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "ws = a[a.index('--cd') + 1] if '--cd' in a else '.'\n"
        f"p = pathlib.Path(ws, {path!r}); p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_text({fix!r})\n"
    ))
    which = {"cortex": str(cortex), "codex": str(codex)}
    real_which = base.shutil.which
    monkeypatch.setattr(base.shutil, "which", lambda n: which.get(n) or real_which(n))

    gov = score_repo_task(task, PRESETS["cortex_wrapped"], CortexCodeGen(PRESETS["cortex_wrapped"], provider="codex"))
    raw = score_repo_task(task, PRESETS["codex_cli_raw"], CodexCodeGen(PRESETS["codex_cli_raw"]))
    for r in (gov, raw):
        assert r.resolved and not r.gen_error and r.tests_passed == r.tests_total > 0
        assert path in r.files


def test_live_failure_surfaces_as_error(tmp_path, monkeypatch):
    task = load_repo_tasks()[0]
    fail = ("task-2 running\ntask-2 failed\n"
            'GatewayClientRequestError: openai:default uses oauth, needs an OpenAI API key profile.')
    cortex = _stub(tmp_path / "cortex", "print(%r)\n" % fail)
    real_which = base.shutil.which
    monkeypatch.setattr(base.shutil, "which", lambda n: str(cortex) if n == "cortex" else real_which(n))

    r = score_repo_task(task, PRESETS["cortex_wrapped"], CortexCodeGen(PRESETS["cortex_wrapped"], provider="codex"))
    assert not r.resolved and r.gen_error and "OpenAI API key" in r.gen_error
