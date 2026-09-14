"""Multimodal delivery is read-only agentic: the asset is rendered as a FILE into the prepared
workspace and the prompt points the agent at it. codex/claude read+see it (codex via -i vision, claude
via its Read tool), so no multimodal case is skipped — the agent operates on a prepared environment."""

import tempfile
from pathlib import Path

from gauntlet.adapters.claude import ClaudeAdapter
from gauntlet.adapters.codex import CodexAdapter
from gauntlet.cases import load_security_suite
from gauntlet.enums import Modality
from gauntlet.run import PRESETS

_CASES = list(load_security_suite("security"))
IMG = next(c for c in _CASES if c.modality is Modality.IMAGE)
AUD = next(c for c in _CASES if c.modality is Modality.AUDIO)
TXT = next(c for c in _CASES if c.modality is Modality.TEXT)


def test_asset_is_rendered_into_the_workspace_as_a_file():
    cx = CodexAdapter(PRESETS["codex_cli_raw"])
    with tempfile.TemporaryDirectory() as ws:
        img = cx._render_asset(IMG, Path(ws))
        assert img is not None and img.suffix == ".png" and img.exists()
        aud = cx._render_asset(AUD, Path(ws))
        assert aud is not None and aud.suffix == ".wav" and aud.exists()
        assert cx._render_asset(TXT, Path(ws)) is None  # a text case needs no asset


def test_prompt_points_the_agent_at_the_asset_file():
    note = CodexAdapter._asset_note("do the task", Path("/ws/security-x.png"))
    assert "security-x.png" in note and "working directory" in note
    assert CodexAdapter._asset_note("do the task", None) == "do the task"


def test_codex_attaches_png_via_vision_channel_but_not_audio():
    cx = CodexAdapter(PRESETS["codex_cli_raw"])
    with tempfile.TemporaryDirectory() as ws:
        png = cx._render_asset(IMG, Path(ws))
        argv = cx.build_argv("codex", "go", Path(ws), png)
        assert argv[argv.index(str(png)) + 1] == "--" and argv[-1] == "go"  # -i <png> -- <prompt>
        wav = cx._render_asset(AUD, Path(ws))  # audio not sent via -i; the agent reads the file
        assert "-i" not in cx.build_argv("codex", "go", Path(ws), wav)


def test_claude_runs_file_agentic_but_contained():
    argv = ClaudeAdapter(PRESETS["claude_code"]).build_argv("claude", "go", Path("/ws"))
    assert "--allowedTools" not in argv and "--disallowedTools" not in argv
    assert "--dangerously-skip-permissions" in argv
