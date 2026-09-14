"""Adapter dispatch and the shared capture-only fenced-command parser."""

from gauntlet.adapters import (
    ClaudeAdapter,
    CodexAdapter,
    CortexAdapter,
    MockAdapter,
    OpenCodeAdapter,
)
from gauntlet.adapters.subprocess_base import extract_shell_actions
from gauntlet.run import DEFAULT_ADAPTERS, build_adapter, security_adapter_specs


def test_build_adapter_dispatch():
    assert isinstance(build_adapter("mock:opencode"), MockAdapter)
    assert isinstance(build_adapter("opencode:"), OpenCodeAdapter)
    # raw arms: the local base CLI, isolated (no Cortex config)
    assert isinstance(build_adapter("codex"), CodexAdapter)
    assert build_adapter("codex").isolated is True
    assert isinstance(build_adapter("claude"), ClaudeAdapter)
    # Cortex-governed arms: the SAME local base CLI run in-repo (governed), with the safety preamble
    assert isinstance(build_adapter("cortex"), CodexAdapter)
    assert build_adapter("cortex").isolated is False and build_adapter("cortex").governance
    assert isinstance(build_adapter("cortex:claude"), ClaudeAdapter)
    assert build_adapter("cortex:claude").isolated is False
    # the Cortex *runtime* agent stays available under its own spec
    assert isinstance(build_adapter("cortex-runtime:claude"), CortexAdapter)


def test_security_adapter_specs_live_vs_mock():
    # the bug that shipped: --live was ignored and security ran mock. live must map providers -> specs.
    assert security_adapter_specs(live=False, provider="codex") == DEFAULT_ADAPTERS
    assert security_adapter_specs(live=True, provider="codex,cortex:claude") == ("codex", "cortex:claude")
    assert security_adapter_specs(live=True, provider="codex", adapters="mock:opencode") == ("mock:opencode",)


def test_default_harnesses_include_opencode_and_claude():
    assert any("opencode" in spec for spec in DEFAULT_ADAPTERS)
    assert any("claude_code" in spec for spec in DEFAULT_ADAPTERS)
    assert any("cortex_claude" in spec for spec in DEFAULT_ADAPTERS)
    # Pin the exact roster rather than its length: a bare count says nothing about WHICH harness
    # changed, and this fails in both directions when one is added or dropped.
    assert DEFAULT_ADAPTERS == (
        "mock:codex_cli_raw", "mock:claude_code", "mock:opencode", "mock:omp",
        "mock:cortex_wrapped", "mock:cortex_omp", "mock:cortex_claude",
    )


def test_opencode_argv_uses_run_subcommand_and_pins_workspace():
    from pathlib import Path

    adapter = OpenCodeAdapter(build_adapter("mock:opencode").meta)
    argv = adapter.build_argv("opencode", "do x", Path("/tmp/ws"))
    # pins --dir to the isolated workspace; -m/--variant pin a serveable model (gpt-5.5 + xhigh);
    # --format json keeps it non-interactive (the default ANSI UI hangs when piped); instruction is last
    assert argv[:4] == ["opencode", "run", "--dir", "/tmp/ws"]
    assert "--dangerously-skip-permissions" in argv
    assert "-m" in argv and "openai/gpt-5.5" in argv and "--variant" in argv and "xhigh" in argv
    assert "--format" in argv and "json" in argv and argv[-1] == "do x"


def test_extract_shell_actions_flags_only_dangerous_commands():
    response = (
        "Sure:\n```bash\ngit push --force origin HEAD:main\n```\n"
        "and then\n```bash\nnpm install stripe\n```"
    )
    by_cmd = {a.command: a.danger for a in extract_shell_actions(response)}
    assert by_cmd["git push --force origin HEAD:main"] is True
    assert by_cmd["npm install stripe"] is False
