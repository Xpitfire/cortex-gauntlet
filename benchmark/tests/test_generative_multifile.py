"""Track G live multi-file: a genuine multi-file app is built, served, and measured end-to-end.

Hermetic — no real model/network/Docker:
- A tiny in-process OpenAI-compatible STUB server (http.server thread) answers POST /chat/completions
  with a fixed reply; LLM_BASE_URL points the served app at it.
- run_e2e drives the multi-file chat-multi fixture (app.py + server/ + templates/ + static/ + tests/)
  and we assert it builds, serves, and passes its REST + static + chat checks. UI checks degrade
  gracefully when Playwright/Chromium is absent (same handling as test_phase3 / test_e2e_probe).
- A unit test asserts run_live_brief builds its CodeGenRequest with capture_repo=True and that
  live_briefs() returns >=2 multi-file briefs each with a valid manifest.
"""

import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from gauntlet.generative.e2e import run_e2e
from gauntlet.generative.judge import HeuristicGenerativeJudge
from gauntlet.generative.live import live_briefs, run_live_brief
from gauntlet.livegen.models import CodeGenRequest, CodeGenResult
from gauntlet.paths import SUITES
from gauntlet.run import PRESETS
from gauntlet.synapse import SynapsePlanner

FIXTURE = SUITES / "generative" / "fixtures" / "chat-multi"

# UI checks (Playwright) and the chat check are tolerant when the browser / a real reply is absent.
_NON_UI_REQUIRED = {"static-css", "static-js", "history"}


class _StubHandler(BaseHTTPRequestHandler):
    """Answers the OpenAI-compatible chat-completions call with a fixed reply."""

    def log_message(self, *args) -> None:  # quiet
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)  # drain the request body
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "pong"}}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _StubSLM:
    """Context manager running the stub OpenAI server on a background thread; yields its base URL."""

    def __enter__(self) -> str:
        self._port = _free_port()
        self._server = HTTPServer(("127.0.0.1", self._port), _StubHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self._port}/v1"

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _manifest() -> dict:
    return json.loads((FIXTURE / "e2e.json").read_text())


def test_multifile_e2e_serves_and_passes_against_stub_slm(tmp_path):
    manifest = _manifest()
    with _StubSLM() as base_url:
        env = {**os.environ, "LLM_BASE_URL": base_url, "LLM_MODEL": "stub"}
        report = run_e2e(FIXTURE, manifest, screenshot=tmp_path / "shot.png", env=env)

    assert report.built and report.served  # the multi-file package booted on 127.0.0.1
    by_id = {c.id: c for c in report.checks}
    # REST + static checks must pass: /static/style.css, /static/app.js, /api/history
    for cid in _NON_UI_REQUIRED:
        assert by_id[cid].passed, f"{cid} failed: {by_id[cid].detail}"
    # the chat round-trip through the stub SLM returns the stubbed reply ("pong")
    assert by_id["send-message"].passed, by_id["send-message"].detail


def _features_from_checks(manifest: dict) -> set[str]:
    return {c["id"] for c in manifest["checks"]}


def test_live_briefs_are_multifile_with_valid_manifests():
    briefs = live_briefs()
    assert len(briefs) >= 2
    seen_ids = set()
    for brief in briefs:
        assert brief["id"] not in seen_ids
        seen_ids.add(brief["id"])
        manifest = brief["manifest"]
        if brief["language"] == "python":
            # python briefs run buildless on the host fallback (no untrusted installer) AND in the sandbox;
            # the instruction must mandate a genuine multi-file layout (server/ package + templates + static)
            instr = brief["instruction"]
            assert "server/handlers.py" in instr and "templates/index.html" in instr
            assert "static/style.css" in instr and "static/app.js" in instr
            assert "tests/" in instr
            assert manifest.get("build") is None  # buildless — host-exec safety, no untrusted installer
            assert manifest["start"][0] == "{python}"
            assert len(manifest["checks"]) >= 6
        else:
            # node/TS briefs are BUILT (pnpm/npm install + tsc) and SERVED ONLY in the Docker sandbox —
            # install/build/serve come from package.json (not the manifest), and the host never runs them.
            assert brief["language"] == "typescript" and brief.get("requires_sandbox") is True
            assert "package.json" in brief["instruction"]
            assert "build" not in manifest and "start" not in manifest  # discover_launch supplies these
            assert len(manifest["checks"]) >= 3
        checks = manifest["checks"]
        # every check has the keys its kind requires
        for chk in checks:
            assert {"id", "kind"} <= chk.keys()
            if chk["kind"] == "ui":
                assert "selector" in chk and "path" in chk
            elif chk["kind"] == "rest":
                assert "method" in chk and "path" in chk and "status" in chk
            elif chk["kind"] == "chat":
                assert "path" in chk and "message" in chk and "min_len" in chk
            else:
                raise AssertionError(f"unknown check kind: {chk['kind']}")
    # the chat brief still drives a static (css/js) + chat round-trip surface
    chat = next(b for b in briefs if b["id"] == "chat-app")
    feats = _features_from_checks(chat["manifest"])
    assert {"static-css", "static-js", "send-message", "history"} <= feats


class _RecordingCodeGen:
    """A fake CodeGenAdapter that records the request and returns a one-file result (no e2e run needed)."""

    def __init__(self, meta) -> None:
        self.meta = meta
        self.request: CodeGenRequest | None = None

    def generate(self, request: CodeGenRequest) -> CodeGenResult:
        self.request = request
        # a non-empty single file so run_live_brief proceeds; the served app failing is irrelevant here
        return CodeGenResult(backend=self.meta.id, main_code="print('hi')\n",
                             files={"app.py": "print('hi')\n"}, ok=True)


def test_run_live_brief_requests_capture_repo(monkeypatch):
    meta = PRESETS["cortex_wrapped"]
    codegen = _RecordingCodeGen(meta)
    brief = next(b for b in live_briefs() if b["id"] == "notes-app")  # deterministic, no SLM
    # This test is purely about the SHAPE of the CodeGenRequest, which run_live_brief records before
    # it reaches the sandbox. `live` imports both names BY VALUE (`from .sandbox import ...`), so they
    # must be patched on `live`, not on the sandbox module. Docker must report AVAILABLE: the guard is
    # the first statement in run_live_brief and would otherwise refuse before any codegen. The sandbox
    # itself is stubbed so the suite stays hermetic and does not pay the ~25s readiness timeout serving
    # the trivial (non-serving) recorded app — the round-trip is irrelevant to the assertions below.
    from gauntlet.generative import live as live_mod
    from gauntlet.generative.e2e import E2EReport
    monkeypatch.setattr(live_mod, "docker_available", lambda: True)
    monkeypatch.setattr(live_mod, "run_generative_sandbox",
                        lambda *a, **k: E2EReport(built=True, served=False))
    run_live_brief(brief, meta, codegen, SynapsePlanner(), HeuristicGenerativeJudge())
    assert codegen.request is not None
    assert codegen.request.capture_repo is True  # the whole repo tree is captured, not just *.py
    assert codegen.request.language == "python"
    assert codegen.request.main_file == "app.py"
