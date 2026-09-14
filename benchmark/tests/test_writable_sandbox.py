"""Track S arms run in a WRITABLE sandbox (no read-only-wall distraction) but stay contained, and the
agent's file writes are captured as the compliance signal (a complying attack often writes to a file
rather than describing it in prose)."""

import tempfile
import time
from pathlib import Path

from gauntlet.adapters.codex import CodexAdapter
from gauntlet.adapters.claude import ClaudeAdapter
from gauntlet.adapters.subprocess_base import _capture_writes, _snapshot
from gauntlet.run import PRESETS


def test_codex_uses_writable_sandbox_not_read_only():
    argv = CodexAdapter(PRESETS["codex_cli_raw"]).build_argv("codex", "do it", Path("/tmp/x"))
    assert "workspace-write" in argv and "read-only" not in argv
    assert "--ignore-user-config" in argv
    governed = CodexAdapter(PRESETS["cortex_wrapped"], isolated=False).build_argv(
        "codex", "do it", Path("/tmp/x"))
    assert "--ignore-user-config" not in governed


def test_codex_security_adapter_allows_managed_task_writes(tmp_path):
    (tmp_path / ".agents" / "tasks").mkdir(parents=True)
    argv = CodexAdapter(PRESETS["cortex_wrapped"], isolated=False).build_argv("codex", "do it", tmp_path)
    writable = [argv[idx + 1] for idx, arg in enumerate(argv) if arg == "--add-dir"]
    assert str(tmp_path / ".agents") in writable
    assert str(tmp_path / ".agents" / "tasks") in writable


def test_claude_uses_full_tool_surface_without_prompts():
    argv = ClaudeAdapter(PRESETS["claude_code"]).build_argv("claude", "do it", Path("/tmp/x"))
    assert "--allowedTools" not in argv and "--disallowedTools" not in argv
    assert "--dangerously-skip-permissions" in argv
    assert "--safe-mode" not in argv  # do not narrow Claude's harness behaviour beyond tool containment


def test_capture_writes_catches_agent_files_and_ignores_noise():
    d = Path(tempfile.mkdtemp())
    (d / "README.md").write_text("# proj\n")
    (d / "keep.txt").write_text("unchanged\n")
    (d / ".git").mkdir()
    (d / ".git" / "HEAD").write_text("ref\n")  # VCS noise must be ignored
    snap = _snapshot(d)
    time.sleep(0.01)
    (d / "README.md").write_text("# proj\nAGENT_ADDED\n")     # modified seeded file
    (d / "new.txt").write_text("AGENT_NEW\n")                 # new file
    written = _capture_writes(d, snap)
    assert "AGENT_ADDED" in written and "new.txt" in written and "AGENT_NEW" in written
    assert "keep.txt" not in written and "HEAD" not in written
