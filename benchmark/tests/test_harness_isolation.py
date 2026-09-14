"""Harness isolation: raw codex/claude/opencode must NOT inherit Cortex's package or environment.

The benchmark compares Cortex (hooks + instructions + policies + governance) against RAW harnesses.
If a raw harness ran in the Cortex repo or inherited Cortex's injected env, it would discover
`.claude`/`.codex`/`.opencode`/`AGENTS.md`/`.agents` config and behave like Cortex — contaminating
every track (S/Q/G/P). These tests drive both execution seams with a fake probe binary that records
its cwd + env, and assert: raw arms run OUTSIDE the repo with a scrubbed env; the Cortex arm runs in
the repo cwd with its env intact (governed by design — that is what is under test).
"""

from __future__ import annotations

import json
import stat
from types import SimpleNamespace
from pathlib import Path

import pytest

from gauntlet.adapters.cortex import CortexAdapter
from gauntlet.adapters.opencode import OpenCodeAdapter
from gauntlet.enums import Modality, Objective, Surface, Technique, Track
from gauntlet.harness_isolation import isolated_env, raw_harness_env
from gauntlet.livegen.base import SubprocessCodeGen
from gauntlet.livegen.models import CodeGenRequest
from gauntlet.models import Case
from gauntlet.run import build_adapter

REPO_ROOT = Path(__file__).resolve().parents[2]  # the Cortex repo that ships .agents/.claude/.codex


def _case() -> Case:
    return Case(
        id="c1", track=Track.SECURITY, surface=Surface.DIRECT_TURN, technique=Technique.DIRECT,
        objective=Objective.SECRET_EXFIL, modality=Modality.TEXT, benign=False, family="probe",
        instruction="do x", canary="", ground_truth="",
    )

# a fake "harness": ignores its args, records cwd + workspace files + env to $PROBE_OUT
_PROBE = """#!/usr/bin/env python3
import json, os
names = (
    "HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
)
with open(os.environ["PROBE_OUT"], "w") as fh:
    json.dump({
        "cwd": os.getcwd(),
        "files": sorted(os.listdir(".")),
        "env": sorted(os.environ.keys()),
        "values": {name: os.environ.get(name, "") for name in names},
    }, fh)
print("```bash\\necho hello\\n```")
"""


@pytest.fixture
def probe(tmp_path: Path) -> Path:
    path = tmp_path / "fake_harness"
    path.write_text(_PROBE)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def governed_root(tmp_path, monkeypatch):
    root = tmp_path / "governance"
    root.mkdir()
    for name in ("AGENTS.md", "CLAUDE.md"):
        (root / name).write_text("Synthetic test governance fixture\n")
    for name in (".agents", ".codex", ".claude", ".opencode"):
        (root / name).mkdir()
    monkeypatch.setattr("gauntlet.adapters.subprocess_base._repo_root", lambda: root)
    monkeypatch.chdir(root)
    return root


def _record(out: Path) -> dict:
    return json.loads(out.read_text())


def _meta():
    return build_adapter("mock:opencode").meta  # a valid HarnessMeta without hand-listing every field


def _under(value: str, base: Path) -> bool:
    return Path(value).resolve().is_relative_to(base.resolve())


# ---- raw_harness_env() unit: no global tool homes or session vars -------------------------------
def test_raw_harness_env_strips_globals_and_sets_sterile_homes(tmp_path: Path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir()
    (home / ".local" / "share" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("codex-auth")
    (home / ".codex" / "config.toml").write_text("mcp leak")
    (home / ".claude.json").write_text(json.dumps({
        "oauthAccount": {"email": "user@example.test"},
        "primaryApiKey": "secret",
        "hasCompletedOnboarding": True,
        "mcpServers": {"leak": {}},
        "projects": {str(REPO_ROOT): {"allowedTools": ["Bash"]}},
    }))
    (home / ".claude" / ".credentials.json").write_text("claude-creds")
    (home / ".claude" / "settings.json").write_text("settings leak")
    (home / ".local" / "share" / "opencode" / "auth.json").write_text("opencode-auth")
    (home / ".config" / "opencode" / "opencode.jsonc").write_text("config leak")
    base = {
        "PATH": "/usr/bin", "HOME": str(home), "ANTHROPIC_API_KEY": "k", "OPENAI_API_KEY": "k",
        "OPENCODE_CONFIG": "/c", "CLAUDE_CONFIG_DIR": "/cc", "CODEX_HOME": "/ch",
        "AGENT_SECRET_HOOK_DISABLE": "1", "AGENT_VENV_HOOK_DISABLE": "1",  # Cortex hook state
        "CORTEX_RUNTIME": "1", "CLAUDECODE": "1", "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
        "CODEX_THREAD_ID": "t", "MCP_TRANSPORT": "stdio",
        # the whole Claude Code session family must be stripped (a raw arm is not a nested session)
        "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_CODE_SESSION_ID": "s", "CLAUDE_CODE_CHILD_SESSION": "1",
        "CLAUDE_CODE_EXECPATH": "/x", "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "8",
    }
    env = raw_harness_env(tmp_path / "ws", base)
    assert env["PATH"] == "/usr/bin"
    for name in ("HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        assert _under(env[name], tmp_path / "ws" / ".gauntlet-raw-home")
    assert "OPENCODE_CONFIG" not in env  # current opencode expects this to be a file, not a dir
    assert Path(env["CODEX_HOME"], "auth.json").read_text() == "codex-auth"
    claude_auth = json.loads(Path(env["CLAUDE_CONFIG_DIR"], ".claude.json").read_text())
    assert claude_auth["oauthAccount"]["email"] == "user@example.test"
    assert claude_auth["hasCompletedOnboarding"] is True
    assert "mcpServers" not in claude_auth and "projects" not in claude_auth
    assert Path(env["CLAUDE_CONFIG_DIR"], ".credentials.json").read_text() == "claude-creds"
    assert Path(env["XDG_DATA_HOME"], "opencode", "auth.json").read_text() == "opencode-auth"
    assert not Path(env["CODEX_HOME"], "config.toml").exists()
    assert not Path(env["CLAUDE_CONFIG_DIR"], "settings.json").exists()
    assert not Path(env["XDG_CONFIG_HOME"], "opencode", "opencode.jsonc").exists()
    for dropped in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AGENT_SECRET_HOOK_DISABLE",
                    "AGENT_VENV_HOOK_DISABLE", "CORTEX_RUNTIME", "CLAUDECODE", "CLAUDE_PROJECT_DIR",
                    "CODEX_THREAD_ID", "MCP_TRANSPORT", "CLAUDE_CODE_ENTRYPOINT",
                    "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_EXECPATH",
                    "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP"):
        assert dropped not in env


def test_isolated_env_strips_parent_session_vars():
    env = isolated_env({"PATH": "/usr/bin", "CODEX_THREAD_ID": "t", "CLAUDECODE": "1"})
    assert env == {"PATH": "/usr/bin"}


def test_raw_harness_env_reads_claude_credentials_from_macos_keychain(tmp_path, monkeypatch):
    from gauntlet import harness_isolation

    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"oauthAccount": {"email": "u@example.test"}}))
    monkeypatch.setattr(harness_isolation.sys, "platform", "darwin")
    monkeypatch.setattr(harness_isolation.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout='{"claudeAiOauth":{"accessToken":"token"}}\n'))

    env = raw_harness_env(tmp_path / "ws", {"PATH": "/usr/bin", "HOME": str(home)})

    creds = Path(env["CLAUDE_CONFIG_DIR"], ".credentials.json")
    assert json.loads(creds.read_text())["claudeAiOauth"]["accessToken"] == "token"


# ---- Track S seam: raw adapter runs outside the repo with a scrubbed env ------------------------
def test_track_s_raw_adapter_runs_isolated(probe: Path, tmp_path: Path, monkeypatch):
    out = tmp_path / "rec.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setenv("AGENT_SECRET_HOOK_DISABLE", "1")  # Cortex hook state present in the parent
    monkeypatch.setenv("CLAUDECODE", "1")  # pretend we launched from inside Claude Code
    monkeypatch.setenv("CODEX_HOME", "/global/codex")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setattr("gauntlet.adapters.subprocess_base.shutil.which", lambda _n: str(probe))

    adapter = OpenCodeAdapter(_meta())
    adapter.run(_case())
    rec = _record(out)

    cwd = Path(rec["cwd"]).resolve()
    assert REPO_ROOT != cwd and REPO_ROOT not in cwd.parents  # not in the repo → no config discovery
    assert ".env" in rec["files"]  # decoy seeded so a secret-exfil attack can actually be taken
    assert "AGENT_SECRET_HOOK_DISABLE" not in rec["env"]  # Cortex hook state scrubbed
    assert "CLAUDECODE" not in rec["env"]  # parent-session identity scrubbed
    assert "CODEX_THREAD_ID" not in rec["env"] and "OPENAI_API_KEY" not in rec["env"]
    assert _under(rec["values"]["CODEX_HOME"], cwd / ".gauntlet-raw-home")
    assert _under(rec["values"]["HOME"], cwd / ".gauntlet-raw-home")
    assert "PATH" in rec["env"] and "PROBE_OUT" in rec["env"]


def test_track_s_opencode_pins_dir_to_isolated_workspace(probe: Path, tmp_path: Path, monkeypatch):
    out = tmp_path / "rec.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setattr("gauntlet.adapters.subprocess_base.shutil.which", lambda _n: str(probe))
    # build_argv pins --dir to the (isolated, outside-repo) workspace, never the repo
    argv = OpenCodeAdapter(_meta()).build_argv("opencode", "do x", Path("/tmp/ws"))
    assert argv[:4] == ["opencode", "run", "--dir", "/tmp/ws"]
    assert "--dangerously-skip-permissions" in argv


# ---- Cortex arm: governed by design — runs in an in-repo decoy with env intact ------------------
def test_cortex_arm_is_not_isolated():
    assert CortexAdapter.isolated is False  # the governed arm is what the comparison measures


def test_cortex_arm_runs_in_repo_decoy_with_env_intact(probe: Path, tmp_path: Path, monkeypatch, governed_root):
    out = tmp_path / "rec.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setenv("AGENT_SECRET_HOOK_DISABLE", "1")
    monkeypatch.setattr("gauntlet.adapters.subprocess_base.shutil.which", lambda _n: str(probe))

    CortexAdapter(_meta(), provider="codex").run(_case())
    rec = _record(out)
    cwd = Path(rec["cwd"]).resolve()
    # decoy workspace UNDER the repo: same secret to face as the raw arms, while Cortex's
    # .codex/.agents/git config discovery (which walks up) still resolves — that is the comparison.
    assert governed_root in cwd.parents and ".gauntlet-decoy" in cwd.parts
    assert ".env" in rec["files"]  # the same decoy the raw arms get
    assert {"AGENTS.md", "CLAUDE.md", ".agents", ".codex", ".claude", ".opencode"} <= set(rec["files"])
    assert "AGENT_SECRET_HOOK_DISABLE" in rec["env"]  # env inherited — the Cortex arm is NOT scrubbed


def test_omp_runs_with_shared_governance_without_private_settings(
    probe: Path, tmp_path: Path, monkeypatch, governed_root,
):
    from shutil import which

    out = tmp_path / "omp-rec.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setattr(
        "gauntlet.adapters.subprocess_base.shutil.which",
        lambda name: str(probe) if name == "omp" else which(name),
    )
    build_adapter("cortex:omp").run(_case())
    rec = _record(out)
    assert {"AGENTS.md", "CLAUDE.md", ".agents"} <= set(rec["files"])
    assert governed_root in Path(rec["cwd"]).parents


def test_cortex_arm_cleanup_race_does_not_fail_cell(probe: Path, tmp_path: Path, monkeypatch, governed_root):
    import gauntlet.adapters.subprocess_base as base

    out = tmp_path / "rec.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setattr("gauntlet.adapters.subprocess_base.shutil.which", lambda _n: str(probe))
    real_rmtree = base.shutil.rmtree
    failed_paths = []

    def flaky_rmtree(path, *args, **kwargs):  # noqa: ANN001 - monkeypatch preserves shutil signature
        candidate = Path(path)
        if ".gauntlet-decoy" in candidate.parts and not kwargs.get("ignore_errors"):
            failed_paths.append(candidate)
            raise OSError(66, "Directory not empty", str(candidate))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(base.shutil, "rmtree", flaky_rmtree)

    transcript = CortexAdapter(_meta(), provider="codex").run(_case())

    assert failed_paths
    assert transcript.response.strip()
    assert out.exists()


# ---- livegen seam (Tracks Q/G/P code-gen): raw arm runs outside the repo with a scrubbed env ----
class _ProbeCodeGen(SubprocessCodeGen):
    binary_name = "probe"

    def build_argv(self, binary, prompt, workspace, main_file):  # noqa: ANN001 - test stub
        return [binary]


def test_livegen_raw_codegen_runs_isolated(probe: Path, tmp_path: Path, monkeypatch):
    out = tmp_path / "rec.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setenv("CORTEX_RUNTIME", "1")  # Cortex env present in the parent
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/global/claude")
    monkeypatch.setenv("OPENCODE_CONFIG", "/global/opencode")
    monkeypatch.setattr("gauntlet.livegen.base.shutil.which", lambda _n: str(probe))

    _ProbeCodeGen(_meta()).generate(CodeGenRequest(prompt="p", language="python", main_file="m.py"))
    rec = _record(out)
    cwd = Path(rec["cwd"]).resolve()
    assert REPO_ROOT != cwd and REPO_ROOT not in cwd.parents  # temp workspace outside the repo
    assert "CORTEX_RUNTIME" not in rec["env"]  # Cortex env scrubbed for the raw arm
    assert _under(rec["values"]["CLAUDE_CONFIG_DIR"], cwd / ".gauntlet-raw-home")
    assert not rec["values"]["OPENCODE_CONFIG"]
    assert "PATH" in rec["env"]
