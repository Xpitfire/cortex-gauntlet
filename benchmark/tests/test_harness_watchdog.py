"""Harness subprocess adapters run under an INACTIVITY watchdog, not a fixed wall.

A steadily-working agent (continuous output or file writes) must finish even past the silence window;
a CLI killed after producing partial output remains an incomplete-budget attempt, not an
evaluable completed response. Both a partial-output hang and an initially silent hang raise
HarnessTimeout rather than publishing a safety score.
"""

import sys

import pytest

from gauntlet.adapters.subprocess_base import SubprocessCliAdapter
from gauntlet.cases import load_security_suite
from gauntlet.enums import Modality
from gauntlet.errors import HarnessTimeout
from gauntlet.run import PRESETS


class _FakeCli(SubprocessCliAdapter):
    """Drives a python one-liner as the 'harness', so a test controls exactly what it streams + when."""

    binary_name = "python3"

    def __init__(self, code: str, **kw) -> None:
        super().__init__(PRESETS["opencode"], **kw)
        self._code = code

    def build_argv(self, binary, instruction, workspace, asset=None):
        return [sys.executable, "-c", self._code]


def _text_case():
    return next(c for c in load_security_suite("security") if c.modality is Modality.TEXT)


def test_continuous_output_is_not_killed_past_the_silence_window():
    # emits for ~2.5s with <=0.2s gaps; inactivity is 1s — a fixed 1s wall would kill it, the watchdog
    # must let it finish because it never goes silent for a full second.
    code = ("import time\n"
            "for i in range(12):\n"
            "    print(f'working {i}', flush=True); time.sleep(0.2)\n"
            "print('FINAL ANSWER: done')\n")
    adapter = _FakeCli(code, timeout_s=1)
    adapter.ceiling_s = 30

    tr = adapter.run(_text_case(), 0)

    assert "FINAL ANSWER: done" in tr.response  # ran to completion, not clipped


def test_partial_output_then_silence_is_not_a_complete_attempt():
    # A partial response before timeout does not establish the final safety outcome.
    code = "import time\nprint('PARTIAL ANSWER before hang', flush=True)\ntime.sleep(10)\n"
    adapter = _FakeCli(code, timeout_s=1)
    adapter.ceiling_s = 30

    with pytest.raises(HarnessTimeout):
        adapter.run(_text_case(), 0)


def test_silent_hang_with_no_output_raises_harness_timeout():
    # never prints anything and never writes a file → a true hang → SKIPPED (HarnessTimeout), excluded
    # from the % rather than scored as a refusal.
    adapter = _FakeCli("import time\ntime.sleep(10)\n", timeout_s=1)
    adapter.ceiling_s = 30

    with pytest.raises(HarnessTimeout):
        adapter.run(_text_case(), 0)
