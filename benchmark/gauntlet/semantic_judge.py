"""Shared semantic judge helpers for live benchmark scoring."""

from __future__ import annotations

import json
import shutil
import subprocess
from .errors import SemanticJudgeUnavailable

CLAUDE_JUDGE_MODEL = "claude-opus-4-8"


def clamp01(value: object) -> float:
    return round(max(0.0, min(1.0, float(value))), 3)


def file_evidence(files: dict[str, str], *, chars: int = 16000, per_file: int = 4000) -> str:
    used, chunks = 0, []
    for path, body in sorted(files.items()):
        if used >= chars:
            break
        head = f"\nFILE: {path}\n"
        text = (body or "")[:per_file]
        chunks.append(head + text)
        used += len(head) + len(text)
    return "\n".join(chunks) or "(no files)"


def json_object(text: str) -> dict:
    objs, depth, start, in_string, escape = [], 0, -1, False, False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start != -1:
                objs.append(text[start : i + 1])
                start = -1
    for blob in reversed(objs):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def assistant_text(raw: str) -> str:
    data = json_object(raw)
    payloads = (data.get("result") or {}).get("payloads") if data else None
    if isinstance(payloads, list):
        text = "\n".join(p["text"] for p in payloads if isinstance(p, dict) and p.get("text"))
        if text.strip():
            return text
    return raw


def claude_json(prompt: str, *, model: str = CLAUDE_JUDGE_MODEL, timeout_s: int = 180) -> dict:
    binary = shutil.which("claude")
    if binary is None:
        raise SemanticJudgeUnavailable("claude CLI not found")
    proc = subprocess.run(
        [binary, "-p", "--model", model, prompt],
        capture_output=True, text=True, timeout=timeout_s, check=False,
    )
    data = json_object(assistant_text(proc.stdout))
    if not data:
        raise SemanticJudgeUnavailable(f"claude judge returned no parseable JSON: {proc.stderr[-400:]}")
    return data


def cortex_json(prompt: str, *, provider: str = "claude", timeout_s: int = 120) -> dict:
    binary = shutil.which("cortex")
    if binary is None:
        raise SemanticJudgeUnavailable("cortex CLI not found")
    proc = subprocess.run(
        [binary, "agent", "ask", "--provider", provider, "--", prompt],
        capture_output=True, text=True, timeout=timeout_s, check=False,
    )
    data = json_object(assistant_text(proc.stdout))
    if not data:
        raise SemanticJudgeUnavailable(f"cortex judge returned no parseable JSON: {proc.stderr[-400:]}")
    return data
