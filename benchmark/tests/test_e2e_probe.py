"""First end-to-end test of the Track P probe → Candidate → score path, WITHOUT Docker.

A minimal real storefront app is served locally; the probe starts it, runs the acceptance REST +
robustness journeys against it, writes result.json; we map it to a Candidate and score it. This
exercises launch→serve→probe→result→Candidate→score for real (the Docker isolation + Playwright UI
are validated separately in a Docker/browser env; here run_ui degrades to unavailable).
"""

import json
import os
import socket
import sys
from pathlib import Path

from gauntlet.project import probe, score_project
from gauntlet.project.corpus import load_project_brief
from gauntlet.project.launch import LaunchPlan
from gauntlet.project.sandbox import _to_candidate

# a minimal but real storefront: home, products API (JSON array), cart, 404 otherwise
_APP = '''
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
PRODUCTS = [{"sku": "boss-tee", "name": "BOSS Tee", "price_cents": 2495}]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="text/html"):
        self.send_response(code); self.send_header("content-type", ctype); self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == "/api/products":
            self._send(200, json.dumps(PRODUCTS).encode(), "application/json")
        elif self.path == "/":
            self._send(200, b"<header><nav>Damen Herren Kinder</nav><button>Warenkorb</button></header>")
        elif self.path == "/cart":
            self._send(200, b"<h1>Warenkorb</h1>")
        else:
            self._send(404, b"not found")
HTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8080"))), H).serve_forever()
'''


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_probe_serves_and_scores_a_real_app(tmp_path: Path):
    brief = load_project_brief()
    work = tmp_path / "repo"
    work.mkdir()
    (work / "app.py").write_text(_APP)
    artifacts = tmp_path / "artifacts"
    acc = tmp_path / "acceptance.json"
    acc.write_text(json.dumps(brief.acceptance))

    port = _free_port()
    os.environ["GAUNTLET_SERVE"] = json.dumps([sys.executable, "app.py"])  # use this interpreter
    os.environ["GAUNTLET_PORT"] = str(port)
    os.environ["GAUNTLET_READY"] = "/"
    try:
        probe.main(["probe", str(work), str(acc), str(artifacts)])
    finally:
        for k in ("GAUNTLET_SERVE", "GAUNTLET_PORT", "GAUNTLET_READY"):
            os.environ.pop(k, None)

    result = json.loads((artifacts / "result.json").read_text())
    assert result["served"] is True
    rest = {r["id"]: r for r in result["rest"]}
    assert rest["list_products"]["passed"] is True  # discovered /api/products → JSON array
    rob = {r["id"]: r for r in result["robustness"]}
    assert rob["unknown_route"]["passed"] is True  # 404, not a 500

    # map → Candidate → score end-to-end
    cand = _to_candidate("e2e", True, {"app.py": _APP}, brief.acceptance, result, LaunchPlan("python"))
    assert cand.built and cand.served
    scored = score_project(brief, cand)
    assert scored.signals.build == 1
    assert scored.signals.composite > 0.0
    assert 0.0 <= scored.signals.security <= 1.0
