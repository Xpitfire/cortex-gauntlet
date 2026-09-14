"""Phase 3: real build + serve + Playwright/REST e2e against a runnable fixture app."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from gauntlet.generative.e2e import run_e2e
from gauntlet.paths import SUITES

FIXTURE = SUITES / "generative" / "fixtures" / "todo-app"
CHAT_FIXTURE = SUITES / "generative" / "fixtures" / "chat-multi"


def _manifest() -> dict:
    return json.loads((FIXTURE / "e2e.json").read_text())


def test_real_e2e_passes_on_a_working_app(tmp_path):
    report = run_e2e(FIXTURE, _manifest(), screenshot=tmp_path / "shot.png")
    assert report.built and report.served
    assert report.total == 5 and report.passed == 5  # 2 real UI checks + 3 REST/state checks
    assert (tmp_path / "shot.png").exists()  # a real Chromium screenshot was captured
    # the state check exercised POST /api/todos then GET reflecting the new item
    assert any(c.id == "state-persists" and c.passed for c in report.checks)


def test_real_e2e_detects_failing_checks(tmp_path):
    m = _manifest()
    m["checks"].append({"id": "missing-el", "kind": "ui", "path": "/", "selector": "#nope", "text": "x"})
    m["checks"].append({"id": "bad-body", "kind": "rest", "method": "GET", "path": "/api/todos",
                        "status": 200, "contains": "THIS_IS_NOT_PRESENT"})
    report = run_e2e(FIXTURE, m, screenshot=tmp_path / "s.png")
    assert report.served
    failed = {c.id for c in report.checks if not c.passed}
    assert {"missing-el", "bad-body"} <= failed and report.passed == 5  # originals still pass


def test_build_gate_fails_closed():
    m = _manifest()
    m["build"] = ["false"]  # a build command that exits non-zero
    report = run_e2e(FIXTURE, m)
    assert report.built is False and report.served is False and report.total == 0


def _read_tree(root) -> dict:
    return {str(p.relative_to(root)): p.read_text()
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


class _MultiFileFake:
    """Fake codegen that "generates" the whole multi-file chat fixture tree (path -> content)."""

    def __init__(self, meta, files: dict) -> None:
        self.meta = meta
        self._files = files

    def generate(self, request):
        from gauntlet.livegen.models import CodeGenResult
        return CodeGenResult(backend=self.meta.id, main_code=self._files.get("app.py", ""),
                             files=dict(self._files), ok=True)


class _StubSLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        body = json.dumps({"choices": [{"message": {"content": "pong"}}]}).encode()
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


def test_track_g_live_pipeline_via_fake_codegen(tmp_path, monkeypatch):
    # Fake codegen stands in for a live CLI: it "generates" the MULTI-FILE chat app, then the REAL
    # e2e runner builds, serves, and browser/REST/chat-tests it against a stub local SLM -> a
    # measured (not modeled) completeness over a genuine multi-file package.
    from gauntlet.generative.judge import HeuristicGenerativeJudge
    from gauntlet.generative.live import live_briefs, run_live_brief
    from gauntlet.run import PRESETS
    from gauntlet.synapse import SynapsePlanner

    brief = next(b for b in live_briefs() if b["id"] == "chat-app")
    files = _read_tree(CHAT_FIXTURE)
    assert "server/handlers.py" in files and "templates/index.html" in files  # truly multi-file

    # Untrusted generated apps must take the real Docker path; host fallback is forbidden.

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _StubSLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GAUNTLET_LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("GAUNTLET_LLM_MODEL", "stub")
    try:
        fake = _MultiFileFake(PRESETS["cortex_wrapped"], files)
        r = run_live_brief(brief, PRESETS["cortex_wrapped"], fake, SynapsePlanner(),
                           HeuristicGenerativeJudge(), assets_dir=tmp_path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert r.build_pass == 1 and r.feature_count == 7
    # the non-UI checks (static css/js + chat round-trip via the stub SLM + history) must pass;
    # UI checks degrade to fail without Chromium, so assert on the measurable functional set.
    by_id = {f.feature_id: f for f in r.rep_features}
    for fid in ("static-css", "static-js", "send-message", "history"):
        assert by_id[fid].passed, f"{fid} did not pass"
    # quality is evaluated over the WHOLE captured tree (server/*, tests/*, app.py)
    assert 0.0 <= r.code_quality <= 1.0 and r.files and len(r.files) >= 7
