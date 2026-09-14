"""Tests for the in-container probe's HTTP logic, against an in-process stub app (no Docker/browser)."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gauntlet.project import probe


class _StubApp(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _reply(self, status: int, body: bytes, ctype: str = "text/html") -> None:
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/products":
            self._reply(200, b'[{"sku":"a","name":"Tee"}]', "application/json")
        elif self.path in ("/", "/cart"):
            self._reply(200, b"<h1>Shop</h1>")
        else:
            self._reply(404, b"not found")


@pytest.fixture
def base():
    server = HTTPServer(("127.0.0.1", 0), _StubApp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_wait_ready(base):
    assert probe.wait_ready(base, "/", timeout=5.0) is True


def test_rest_discovers_product_list(base):
    results = probe.check_rest(base, [{"id": "list_products"}, {"id": "create_order"}])
    by_id = {r["id"]: r for r in results}
    assert by_id["list_products"]["passed"] is True
    assert "list of" in by_id["list_products"]["detail"]  # e.g. "/api/products -> list of 1"
    assert by_id["create_order"]["passed"] is False  # POST/state contract → unverified, not faked


def test_robustness_unknown_route_404(base):
    results = probe.check_robustness(base, [{"id": "unknown_route"}, {"id": "empty_cart"}])
    by_id = {r["id"]: r for r in results}
    assert by_id["unknown_route"]["passed"] is True  # 404, not a 500
    assert by_id["empty_cart"]["passed"] is True  # /cart returns < 500


def test_ui_guarded_without_browser(base):
    # no Playwright/browser in this env → run_ui degrades gracefully, never raises
    out = probe.run_ui(base, {"visual_anchors": [], "journeys": []}, "/tmp/gx_probe_artifacts")
    assert out.get("available") in (False, True)
