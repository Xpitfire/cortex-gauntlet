"""Resilience for live benchmark runs: classify rate limits, back off, checkpoint, and resume.

Live coding-agent CLIs hit provider rate limits. A rate limit must never be recorded as a task failure
— that would understate a harness and hide the real cause. Instead we retry with bounded backoff
(absorbing transient limits), and if the limit persists we pause the run with a checkpoint so it can
resume once the limit clears, rather than idling forever or faking a failure.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

# provider rate-limit / overload signatures across codex / claude / openai / anthropic CLIs
_RATE_LIMIT = re.compile(
    r"\b(?:429|529)\b|rate[\s_-]?limit|too many requests|quota\s*exceeded|insufficient_quota"
    r"|overloaded|resource[\s_-]?exhausted|try again later|retry[\s-]?after|temporarily unavailable",
    re.IGNORECASE,
)


def is_rate_limited(text: str) -> bool:
    """True if text looks like a provider rate-limit / overload signal (not a normal error)."""
    return bool(text) and _RATE_LIMIT.search(text) is not None


# Provider auth-failure signatures (the harness CLI lost its session mid-run, e.g. Claude logged out).
# Deliberately specific — NOT a bare "401", because case content legitimately mentions things like
# "users report 401s under load"; we only match the CLI's own authentication-failure phrasing.
_AUTH_ERROR = re.compile(
    r"failed to authenticate|invalid authentication credentials|invalid api key|not authenticated"
    r"|authentication[_\s-]?error|oauth token (?:expired|invalid|revoked)|session (?:expired|invalid)"
    r"|please (?:run|sign|log)\b[^.\n]*\b(?:login|/login|sign in|log in)"
    r"|401[^.\n]*(?:unauthorized|invalid authentication|credentials|expired)",
    re.IGNORECASE,
)


def is_auth_error(text: str) -> bool:
    """True if text is a provider AUTHENTICATION failure (the CLI lost its session) — an infra problem
    to pause+retry on (re-auth, then resume), never a task pass/fail. Distinct from a rate limit."""
    return bool(text) and _AUTH_ERROR.search(text) is not None


# Lost connectivity / a transient API/server error — the laptop dropped Wi-Fi, the provider 5xx'd, a
# DNS/TLS hiccup. Like a rate limit/auth failure, this is infra (never a task pass/fail): pause so the
# user can reconnect and resume exactly where they left off, rather than recording an invalid result.
_CONNECTION_ERROR = re.compile(
    r"connection (?:error|refused|reset|aborted|closed|timed out)|could not connect|failed to connect"
    r"|network (?:is )?(?:unreachable|down|error)|temporary failure in name resolution|getaddrinfo"
    r"|name or service not known|dns\b|ssl error|sslerror|ssl:\s|handshake (?:fail|error|timed?\s*out)"
    r"|certificate[\s_]*verif"
    r"|read timed out|request timed out|connection timed out|broken pipe|remote end closed"
    r"|econnreset|econnrefused|enetunreach|etimedout|enotfound|eai_again"
    r"|service unavailable|bad gateway|gateway time-?out|upstream connect error"
    r"|api error: 5\d\d|http 5\d\d|status 5\d\d|internal server error"
    r"|you are offline|appears? to be offline|no internet connection|network connection lost",
    re.IGNORECASE,
)


def is_connection_error(text: str) -> bool:
    """True if text looks like lost connectivity or a transient server/API error (pause + resume)."""
    return bool(text) and _CONNECTION_ERROR.search(text) is not None


def is_infra_error(text: str) -> bool:
    """Any non-task infra failure that should PAUSE (not fail) a run: rate limit, auth loss, or lost
    connectivity / a transient API server error."""
    return is_rate_limited(text) or is_auth_error(text) or is_connection_error(text)


def backoff_delays(retries: int, base: float = 5.0, cap: float = 60.0) -> list[float]:
    """Exponential backoff sequence (seconds), capped: base, 2·base, 4·base, … (each ≤ cap)."""
    return [min(cap, base * (2**i)) for i in range(max(0, retries))]


# Smart default: 3 retries with the capped exponential backoff above ⇒ up to ~35s (5+10+20) spent
# absorbing a *transient* rate limit before pausing. Long enough for a brief provider 429 to clear,
# short enough that a *sustained* limit pauses (checkpoint + resume) instead of idling for minutes.
DEFAULT_RATELIMIT_RETRIES = 3


def rate_limit_retries() -> int:
    """Retry budget for transient rate limits. The smart default ({DEFAULT_RATELIMIT_RETRIES}) is
    overridable via GAUNTLET_RATELIMIT_RETRIES (CLI `--rate-limit-retries`); 0 pauses immediately."""
    try:
        return max(0, int(os.environ.get("GAUNTLET_RATELIMIT_RETRIES", str(DEFAULT_RATELIMIT_RETRIES))))
    except ValueError:
        return DEFAULT_RATELIMIT_RETRIES


def rate_limit_retry(
    run_once: Callable[[], object],
    limited: Callable[[object], bool],
    *,
    retries: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_wait: Callable[[int, float], None] | None = None,
) -> tuple[object, bool]:
    """Call run_once() until its result is not rate-limited or the retry budget is spent.

    `limited(result)` decides whether to retry; backoff is slept between attempts. Returns
    (last_result, was_still_limited). on_wait(attempt, delay) is a notifier hook for the UI.
    """
    delays = backoff_delays(rate_limit_retries() if retries is None else retries)
    result = run_once()
    for attempt, delay in enumerate(delays):
        if not limited(result):
            return result, False
        if on_wait is not None:
            on_wait(attempt + 1, delay)
        sleep(delay)
        result = run_once()
    return result, limited(result)


class Checkpoint:
    """Append-only JSONL checkpoint of completed cells (keyed by a stable cell id) for resume.

    One JSON object per line — {"key": <cell key>, "outcome": {...}}. Append-only so a crash or pause
    mid-run never corrupts earlier progress; a resumed run reads the keys already done and skips them.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def completed(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.path.exists():
            return out
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a torn final line from an interrupted write
            if isinstance(rec, dict) and "key" in rec:
                out[rec["key"]] = rec.get("outcome", {})
        return out

    def put(self, key: str, outcome: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "outcome": outcome}, ensure_ascii=False) + "\n")
