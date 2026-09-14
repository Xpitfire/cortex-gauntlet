"""Fixture full-stack app (stdlib only): UI + REST + in-memory state.

Used to prove the real build->serve->Playwright/REST e2e runner end-to-end without a live
harness. A real harness's generated app is driven the same way.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

TODOS: list[dict] = []

PAGE = b"""<!doctype html><html><head><title>Todos</title></head>
<body><h1 id="title">Todos</h1><ul id="list"></ul>
<form id="f"><input id="t" name="t"/><button type="submit">add</button></form>
<script>
async function load(){const r=await fetch('/api/todos');const d=await r.json();
document.getElementById('list').innerHTML=d.map(x=>'<li>'+x.title+'</li>').join('');}
document.getElementById('f').onsubmit=async (e)=>{e.preventDefault();
await fetch('/api/todos',{method:'POST',body:JSON.stringify({title:document.getElementById('t').value})});
await load();};
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
        elif self.path == "/api/todos":
            self._json(200, TODOS)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/todos":
            n = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            TODOS.append({"title": body.get("title", "")})
            self._json(201, {"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args) -> None:  # quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
