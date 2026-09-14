"""A tiny stdlib OpenAI-compatible SLM stub — runs as a sidecar container on the sandbox's internal net.

The Track G live sandbox runs the generated app on an `--internal` docker network with this stub at a
fixed network-alias (e.g. `slm`). The app's LLM_BASE_URL points here, so the chat round-trip is exercised
with ZERO host/WAN egress — the candidate can reach ONLY this stub, nothing else.

Endpoints (OpenAI-compatible):
- POST /v1/chat/completions and POST /chat/completions → 200 with `choices[0].message.content`. The
  content echoes the last user message when present, else "pong".
- GET  /v1/models and GET /models → 200 with a minimal model list.

Stdlib only (mirrors the in-test stub used by test_generative_multifile.py). Binds 0.0.0.0 on $PORT so
the candidate reaches it by network alias.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


def _reply_for(body: bytes) -> str:
    """Echo the last user message when the request is a well-formed chat request, else 'pong'."""

    try:
        data = json.loads(body or b"{}")
        messages = data.get("messages")
        if isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return "pong"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet
        pass

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models") or self.path.rstrip("/") in ("/v1", ""):
            self._json(200, {"object": "list", "data": [{"id": "stub", "object": "model"}]})
        else:
            self._json(200, {"status": "ok"})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length) if length else b""
        if self.path.rstrip("/").endswith("/chat/completions"):
            reply = _reply_for(raw)
            self._json(200, {"id": "stub", "object": "chat.completion", "model": "stub",
                             "choices": [{"index": 0, "finish_reason": "stop",
                                          "message": {"role": "assistant", "content": reply}}]})
        else:
            self._json(404, {"error": "not found"})


def serve(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _Handler)  # noqa: S104 — sidecar on a private docker network only
    server.serve_forever()


if __name__ == "__main__":
    serve(int(os.environ.get("PORT", "8000")))
