"""OpenAI-compatible SLM client over urllib (stdlib only).

POSTs to {LLM_BASE_URL}/chat/completions with {"model": LLM_MODEL, "messages": [...]} and returns
choices[0].message.content. On any failure it returns a valid fallback reply so the chat route never
500s — the app stays servable even when the local model is down.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

_FALLBACK = "Sorry, the assistant is unavailable right now."


def parse_completion(payload: dict[str, Any]) -> str:
    """Pull choices[0].message.content out of an OpenAI chat-completions response."""

    choices = payload.get("choices") or []
    if choices:
        return (choices[0].get("message") or {}).get("content", "") or ""
    return ""


def complete(messages: list[dict[str, str]], timeout: float = 60.0) -> str:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "qwen2.5:0.5b")
    body = json.dumps({"model": model, "messages": messages}).encode()
    request = urllib.request.Request(
        base + "/chat/completions", data=body, method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode(errors="replace"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return _FALLBACK
    return parse_completion(payload) or _FALLBACK
