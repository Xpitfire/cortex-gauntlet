"""Multi-file fixture chat app (stdlib only): entry point.

Reference app for the live Track G "chat-app" brief — a ChatGPT-style assistant wired to a
LOCAL OpenAI-compatible SLM. Proves the build->serve->Playwright/REST/chat e2e runner against a
genuine multi-file package (server/ + templates/ + static/ + tests/) without a live harness.
Run: `python app.py <port>` — binds 127.0.0.1 only.
"""

from __future__ import annotations

import sys
from http.server import HTTPServer

from server.handlers import Handler


def main(argv: list[str]) -> None:
    port = int(argv[1]) if len(argv) > 1 else 8000
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(sys.argv)
