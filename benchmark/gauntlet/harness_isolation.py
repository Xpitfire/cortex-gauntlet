"""Isolation for live harness subprocesses — keep Cortex's package out of the *raw* harnesses.

The benchmark compares Cortex (which ships hooks, instructions, policies, governance) against RAW
codex / omp / claude / opencode. If a raw harness ran in the Cortex repo (or inherited Cortex's injected
environment), it would discover `.claude/settings.json`, `.codex/`, `.omp/`, `.opencode/`, `AGENTS.md`,
`CLAUDE.md`, `.agents/` and run with Cortex's behaviour — contaminating the comparison for EVERY
track (S/Q/G/P). Two guarantees keep the arms clean:

1. cwd isolation: a raw harness runs in a fresh temp workspace OUTSIDE the repo tree, so per-project
   config discovery (which walks up from the cwd / `--dir` / `--cd`) never reaches the repo's config.
2. env isolation: raw harnesses get a sterile HOME/CODEX_HOME/CLAUDE_CONFIG_DIR/XDG_* home
   inside the temp workspace, so user-global skills, MCP servers, hooks, memories, and session state
   cannot leak in. Only allowlisted provider auth files are linked in from global or GAUNTLET_*
   credential sources, so live experiments reuse logins without importing executable behaviour.

The Cortex arm is deliberately NOT isolated — being governed by the Cortex runtime is exactly what is
under test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Prefixes for variables that carry Cortex/agent or parent-session behaviour.
_DENY_PREFIXES = (
    "AGENT_",  # Cortex hook bypass/state (e.g. AGENT_*_HOOK_DISABLE) injected by the .agents hooks
    "CORTEX_",  # Cortex runtime/CLI configuration
    "CODEX_",  # Codex session/config state; raw arms get explicit sterile homes below
    "OMP_",  # OMP profile/broker/session state; raw arms get explicit sterile homes below
    "PI_",  # OMP's legacy/runtime env namespace
    # ALL Claude Code session/behaviour vars (ENTRYPOINT, SSE_PORT, SESSION_ID, CHILD_SESSION,
    # EXECPATH, STOP_HOOK_BLOCK_CAP, …) — a raw arm must not look like a nested Claude Code session.
    "CLAUDE_CODE_",
    "MCP_",  # MCP transport/session variables
)
# Exact variables that signal "running inside Claude Code" or pin a parent project dir.
_DENY_EXACT = frozenset({
    "ANTHROPIC_API_KEY",
    "CLAUDECODE",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR",
    "OPENAI_API_KEY",
    "OPENCODE_CONFIG",
})
_RAW_ALLOW = frozenset({"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "PROBE_OUT"})
_RAW_DIRS = {
    "HOME": "home",
    "XDG_CONFIG_HOME": "xdg-config",
    "XDG_DATA_HOME": "xdg-data",
    "XDG_CACHE_HOME": "xdg-cache",
    "CODEX_HOME": "codex",
    "CLAUDE_CONFIG_DIR": "claude",
}
_CLAUDE_JSON_AUTH_KEYS = frozenset({
    "oauthAccount", "primaryApiKey", "hasCompletedOnboarding", "lastOnboardingVersion",
    "userID", "userEmail", "account", "accountId", "organizationId",
})
_CODEX_WRITABLE_RELS = (
    ".agents", ".agents/tasks", ".agents/tasks/plans", ".agents/tasks/prompts",
    ".claude", ".codex", ".opencode", ".cortex", ".github", ".husky",
)


def _is_denied(name: str) -> bool:
    return name in _DENY_EXACT or name.startswith(_DENY_PREFIXES)


def isolated_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of the environment with Cortex/agent + parent-session variables removed.

    This is for trusted helper subprocesses. Raw benchmark harnesses use `raw_harness_env`.
    """

    source = os.environ if base is None else base
    return {name: value for name, value in source.items() if not _is_denied(name)}


def codex_workspace_write_args(workspace: Path) -> list[str]:
    """Make extracted managed-project subtrees writable inside Codex's workspace-write sandbox."""

    args: list[str] = []
    for rel in _CODEX_WRITABLE_RELS:
        path = workspace / rel
        if path.is_dir():
            args += ["--add-dir", str(path)]
    return args


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _first_file(*paths: Path | None) -> Path | None:
    return next((path for path in paths if path is not None and path.is_file()), None)


def _link_auth(source: Path | None, target: Path) -> None:
    if source is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    try:
        target.symlink_to(source)
    except OSError:
        shutil.copy2(source, target)


def _copy_claude_auth_json(source: Path | None, target: Path) -> None:
    if source is None:
        return
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    auth = {key: data[key] for key in _CLAUDE_JSON_AUTH_KEYS if key in data}
    if not auth:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(auth), encoding="utf-8")


def _copy_claude_keychain_credentials(target: Path) -> None:
    if sys.platform != "darwin":
        return
    try:
        proc = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5, check=False)
    except (subprocess.SubprocessError, OSError):
        return
    raw = proc.stdout.strip()
    if proc.returncode != 0 or not raw:
        return
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw, encoding="utf-8")


def _seed_auth(root: Path, source: dict[str, str]) -> None:
    home = _path(source.get("GAUNTLET_AUTH_HOME") or source.get("HOME"))
    codex_home = _path(source.get("GAUNTLET_CODEX_HOME")) or (home / ".codex" if home else None)
    claude_dir = _path(source.get("GAUNTLET_CLAUDE_CONFIG_DIR")) or (home / ".claude" if home else None)
    opencode_data = _path(source.get("GAUNTLET_OPENCODE_DATA_HOME"))
    if opencode_data is None and home is not None:
        opencode_data = home / ".local" / "share" / "opencode"

    _link_auth(_first_file(_path(source.get("GAUNTLET_CODEX_AUTH_JSON")),
                           codex_home / "auth.json" if codex_home else None),
               root / "codex" / "auth.json")
    _copy_claude_auth_json(_first_file(_path(source.get("GAUNTLET_CLAUDE_AUTH_JSON")),
                                       claude_dir / ".claude.json" if claude_dir else None,
                                       home / ".claude.json" if home else None),
                           root / "claude" / ".claude.json")
    claude_credentials = root / "claude" / ".credentials.json"
    _link_auth(_first_file(_path(source.get("GAUNTLET_CLAUDE_CREDENTIALS_JSON")),
                           claude_dir / ".credentials.json" if claude_dir else None,
                           home / ".claude" / ".credentials.json" if home else None),
               claude_credentials)
    if not claude_credentials.exists():
        _copy_claude_keychain_credentials(claude_credentials)
    _link_auth(_first_file(_path(source.get("GAUNTLET_OPENCODE_AUTH_JSON")),
                           opencode_data / "auth.json" if opencode_data else None),
               root / "xdg-data" / "opencode" / "auth.json")
    omp_agent = root / "home" / ".omp" / "agent"
    _link_auth(_first_file(_path(source.get("GAUNTLET_OMP_AGENT_DB")),
                           home / ".omp" / "agent" / "agent.db" if home else None),
               omp_agent / "agent.db")


def raw_harness_env(workspace: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """Sterile env for raw arms; only auth files are linked from global/GAUNTLET sources."""

    source = os.environ if base is None else base
    root = workspace / ".gauntlet-raw-home"
    env = {name: value for name, value in source.items() if name in _RAW_ALLOW}
    for name, rel in _RAW_DIRS.items():
        path = root / rel
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    _seed_auth(root, source)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env
