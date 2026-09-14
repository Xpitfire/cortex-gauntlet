"""HTTP routing: GET / -> the chat shell, GET /static/<file>, POST /api/chat, GET /api/history."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .llm import complete
from .store import ConversationStore

# project root = the directory that holds templates/ and static/ (parent of this server/ package)
_ROOT = Path(__file__).resolve().parent.parent
_CONTENT_TYPES = {".css": "text/css", ".js": "application/javascript", ".html": "text/html"}

STORE = ConversationStore()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: object) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _static(self) -> None:
        name = Path(self.path[len("/static/"):]).name  # basename only — no path traversal
        target = _ROOT / "static" / name
        if not name or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, (_ROOT / "templates" / "index.html").read_bytes(), "text/html")
        elif self.path.startswith("/static/"):
            self._static()
        elif self.path == "/api/history":
            self._json(200, STORE.history())
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("content-length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            data = {}
        message = str(data.get("message", ""))
        STORE.add("user", message)
        reply = complete(STORE.history())
        STORE.add("assistant", reply)
        self._json(200, {"reply": reply})
