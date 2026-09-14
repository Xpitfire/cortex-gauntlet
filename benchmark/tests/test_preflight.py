"""Provider preflight + Cortex-arm binding.

The Cortex arm wraps the local base CLI (codex / Claude Code) and is driven through the Synapse loop —
so it needs only the local tool on PATH, not a remotely-authed runtime. The preflight catches a missing
prerequisite up front (with the fix) instead of failing after a long live run.
"""

import gauntlet.preflight as pf
from gauntlet.livegen.adapters import (
    ClaudeCodeGen,
    CodexCodeGen,
    CortexCodeGen,
    build_codegen,
)
from gauntlet.preflight import check_providers
from gauntlet.run import PRESETS


def test_cortex_arm_wraps_the_local_base_cli():
    # the governed arm is the SAME local CLI as the raw arm, pinned to the same model — not the runtime
    cortex = build_codegen("cortex", PRESETS["cortex_wrapped"])
    assert isinstance(cortex, CodexCodeGen) and cortex.model == "gpt-5.5"
    cortex_claude = build_codegen("cortex:claude", PRESETS["cortex_claude"])
    assert isinstance(cortex_claude, ClaudeCodeGen) and cortex_claude.model == "opus"
    # the raw arm is the same adapter type (difference is the Synapse loop, via harness.uses_synapse)
    assert isinstance(build_codegen("codex", PRESETS["codex_cli_raw"]), CodexCodeGen)
    # the remote-runtime path stays available behind an explicit token
    assert isinstance(build_codegen("cortex-runtime", PRESETS["cortex_wrapped"]), CortexCodeGen)


def test_preflight_cortex_needs_only_the_local_cli(monkeypatch):
    monkeypatch.setattr(pf.shutil, "which", lambda n: "/usr/bin/" + n if n in ("codex", "claude") else None)
    rt = {"reachable": True, "openai_key": False, "provider_ready": {}}  # runtime has NO OpenAI key…
    ready = {r.provider: r for r in check_providers(["codex", "cortex", "cortex:claude"], runtime=rt)}
    # …yet the Cortex arms are runnable, because they use the local CLI rather than the runtime
    assert ready["cortex"].ok and ready["cortex:claude"].ok and ready["codex"].ok


def test_preflight_flags_missing_cli_and_runtime_gap(monkeypatch):
    monkeypatch.setattr(pf.shutil, "which", lambda n: None)  # nothing installed
    rt = {"reachable": True, "openai_key": False, "provider_ready": {"claude": True}}
    by = {r.provider: r for r in check_providers(["codex", "cortex-runtime", "cortex-runtime:claude"], runtime=rt)}
    assert not by["codex"].ok and "codex CLI" in by["codex"].reason
    # the runtime-over-codex path is the one that truly needs an OpenAI API key
    assert not by["cortex-runtime"].ok and "OpenAI API key" in by["cortex-runtime"].reason
    assert "OPENAI_API_KEY" in by["cortex-runtime"].remedy
    assert by["cortex-runtime:claude"].ok  # claude provider authed in the runtime


def test_opencode_unauthenticated_is_dropped(monkeypatch):
    # opencode on PATH but its probe hangs/errors (no credentials) -> dropped with a fix, not "ok"
    import subprocess
    monkeypatch.setattr(pf.shutil, "which", lambda _n: "/usr/bin/opencode")

    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="opencode", timeout=k.get("timeout", 35))
    monkeypatch.setattr(pf.subprocess, "run", _hang)
    r = check_providers(["opencode"], runtime={})[0]
    assert r.provider == "opencode" and r.ok is False and "auth login" in r.remedy


def test_opencode_authenticated_is_ok(monkeypatch):
    import subprocess
    monkeypatch.setattr(pf.shutil, "which", lambda _n: "/usr/bin/opencode")
    monkeypatch.setattr(pf.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout='{"text":"ready"}', stderr=""))
    r = check_providers(["opencode"], runtime={})[0]
    assert r.ok is True


def test_opencode_token_invalidated_has_specific_remedy(monkeypatch):
    import subprocess
    monkeypatch.setattr(pf.shutil, "which", lambda _n: "/usr/bin/opencode")
    monkeypatch.setattr(
        pf.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout='{"error":"token_invalidated"}', stderr=""))
    r = check_providers(["opencode"], runtime={})[0]
    assert r.ok is False
    assert r.reason == "opencode auth token invalidated"
    assert "opencode auth login" in r.remedy
