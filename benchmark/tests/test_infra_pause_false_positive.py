"""A SUCCESSFUL harness answer that merely discusses rate-limiting / auth / connectivity must NOT be
mistaken for a provider infra failure. The infra pause reads the STRUCTURED transcript.error (set only
when the CLI errored with no real answer), not the legitimate response content."""

import subprocess

from gauntlet.adapters.subprocess_base import SubprocessCliAdapter
from gauntlet.models import Transcript
from gauntlet.run import PRESETS
from gauntlet.tui.bridge import _infra_pause


def _emit(_chunk):
    pass


def test_successful_answer_mentioning_429_does_not_pause():
    # the reported bug: codex works fine but its answer discusses 429/rate-limit/overloaded → false pause
    for answer in [
        "The upstream API returns 429 Too Many Requests; add exponential backoff and retry-after.",
        "Health check failed: the service was temporarily unavailable under load.",
        "The registry looked overloaded; try again later or add a retry.",
        "Implement rate-limit handling so the client backs off on 429.",
    ]:
        t = Transcript("codex_cli_raw", "gpt-5.5", "p", answer, [], 10, 0, error="")
        assert _infra_pause(t.error or "", _emit) is None, answer


def test_real_infra_failure_still_pauses():
    for err in ["Error: 429 rate limit exceeded; retry-after 30s",
                "Failed to authenticate. 401 Invalid authentication credentials",
                "Connection reset by peer"]:
        t = Transcript("codex_cli_raw", "gpt-5.5", "p", "", [], 0, 0, error=err)
        assert _infra_pause(t.error or "", _emit) is not None, err


def _transcript_error(stdout, stderr, rc, written=""):
    """Mirror SubprocessCliAdapter.run's cli_error rule."""
    proc = subprocess.CompletedProcess([], rc, stdout=stdout, stderr=stderr)
    had_real_output = bool((proc.stdout or "").strip()) or bool(written.strip())
    return "" if (rc == 0 or had_real_output) else (proc.stderr or "").strip()


def test_cli_error_is_only_set_on_actual_failure():
    # exit 0 with an answer that says 429 → no error (no false pause)
    assert _transcript_error("answer mentions 429 and rate limit", "", 0) == ""
    # exit non-zero, empty stdout, infra stderr → error captured (real failure)
    assert "429" in _transcript_error("", "Error 429 rate limit", 1)
    # exit non-zero but the agent wrote a real file (acted) → not an infra error, score it
    assert _transcript_error("", "warn: noisy", 1, written="# package.json\n{...}") == ""
    # the SubprocessCliAdapter exposes _response_text used by run()
    proc = subprocess.CompletedProcess([], 0, stdout="hello", stderr="")
    assert SubprocessCliAdapter(PRESETS["codex_cli_raw"])._response_text(proc) == "hello"
