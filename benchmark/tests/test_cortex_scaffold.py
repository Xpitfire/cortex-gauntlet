"""The Cortex 'wrapping' is the project TEMPLATE (instructions, hooks, checks, scripts, adapters) laid
into the harness workspace + the Synapse loop — not the loop alone. These tests pin that the governed
arm actually materializes the scaffold, that the loop credits/repairs only the harness-authored app
(never the generic scaffold), that a missing scaffold FAILS FAST instead of silently downgrading to a
plain harness, and that the live stream collapses a CLI's redraw frames.
"""

import json
import stat
from pathlib import Path

import pytest

from gauntlet.bootstrap import app_files, scaffold_paths, template_available
from gauntlet.errors import HarnessSetupError
from gauntlet.livegen.adapters import CodexCodeGen
from gauntlet.livegen.base import SubprocessCodeGen
from gauntlet.livegen.models import CodeGenRequest
from gauntlet.livegen.progress import ProgressReporter
from gauntlet.project.corpus import load_project_brief
from gauntlet.project.synapse_build import _repair_prompt, generate_repo, observe_requirements
from gauntlet.run import PRESETS

_GOVERNED = PRESETS["cortex_wrapped"]


class _StartupProbeCodeGen(SubprocessCodeGen):
    binary_name = "probe"

    def build_argv(self, binary, prompt, workspace, main_file):  # noqa: ANN001 - test stub
        return [binary, prompt, main_file]


def _need_template():
    if not template_available():
        pytest.skip("project template archive not present")


def _startup_probe(path: Path) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "cwd = pathlib.Path.cwd()\n"
        "main_file = sys.argv[2]\n"
        "pathlib.Path(main_file).write_text('x = 1\\n')\n"
        "paths = {\n"
        "    'AGENTS.md': (cwd / 'AGENTS.md').is_file(),\n"
        "    'CLAUDE.md': (cwd / 'CLAUDE.md').is_file(),\n"
        "    '.agents/instructions.md': (cwd / '.agents' / 'instructions.md').is_file(),\n"
        "    '.agents/hooks': (cwd / '.agents' / 'hooks').is_dir(),\n"
        "    '.codex/config.toml': (cwd / '.codex' / 'config.toml').is_file(),\n"
        "    '.codex/hooks.json': (cwd / '.codex' / 'hooks.json').is_file(),\n"
        "    '.claude/settings.json': (cwd / '.claude' / 'settings.json').is_file(),\n"
        "}\n"
        "record = {\n"
        "    'cwd': str(cwd),\n"
        "    'prompt': sys.argv[1],\n"
        "    'paths': paths,\n"
        "    'codex_home': os.environ.get('CODEX_HOME', ''),\n"
        "    'claude_config_dir': os.environ.get('CLAUDE_CONFIG_DIR', ''),\n"
        "}\n"
        "pathlib.Path(os.environ['PROBE_OUT']).write_text(json.dumps(record))\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---- the scaffold is real, and the loop separates it from app code -----------
def test_scaffold_paths_expose_the_cortex_wrapping():
    _need_template()
    paths = scaffold_paths()
    # the instructions/hooks/checks/scripts/adapters the user expects to see in a Cortex project
    for token in (".agents/instructions.md", "CLAUDE.md", "AGENTS.md", "Makefile"):
        assert token in paths, f"the Cortex scaffold must ship {token}"
    assert any(p.startswith(".cortex/") for p in paths)
    assert any(p.startswith(".agents/hooks/") for p in paths)


def test_app_files_subtracts_the_scaffold():
    _need_template()
    scaffold_key = next(iter(scaffold_paths()))
    files = {
        scaffold_key: "x",
        ".gauntlet-raw-home/codex/sessions/run.jsonl": "runtime",
        ".DS_Store": "finder metadata",
        "src/server/index.ts": "y",
    }
    assert app_files(files) == {"src/server/index.ts": "y"}  # only the harness-authored file remains


def test_loop_observes_app_files_not_the_scaffold():
    # a repo that is ONLY scaffold content must not spuriously satisfy storefront markers — otherwise the
    # generic template's own services/docs would stall the loop before the real storefront is built.
    _need_template()
    scaffold_key = next(p for p in scaffold_paths() if p.endswith((".md", ".ts", ".py", ".json")))
    only_scaffold = {scaffold_key: "stripe checkout cart products payment intent service worker"}
    assert observe_requirements(app_files(only_scaffold)) == set()


# ---- the governed arm materializes the scaffold into its workspace -----------
def test_governed_arm_seeds_the_cortex_scaffold():
    _need_template()
    import tempfile
    from pathlib import Path

    adapter = CodexCodeGen(_GOVERNED)
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        adapter._seed_scaffold(ws, None)
        assert (ws / ".agents" / "instructions.md").exists()  # instructions
        assert (ws / ".agents" / "hooks").is_dir()            # hooks
        assert (ws / ".cortex").is_dir() and (ws / "CLAUDE.md").exists()  # cortex docking + adapter


def test_seeded_scaffold_is_captured_into_the_repo():
    # the exact reported symptom: '.agents/.codex/.cortex are not in the file system'. Seeding + the
    # repo capture must put them in the candidate's files so they show up in the run's repo viewer.
    _need_template()
    import tempfile
    from pathlib import Path

    from gauntlet.livegen.base import _capture_repo

    adapter = CodexCodeGen(_GOVERNED)
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        adapter._seed_scaffold(ws, None)
        (ws / "src" / "server.ts").parent.mkdir(parents=True)  # the harness adds its app on top
        (ws / "src" / "server.ts").write_text("// storefront")
        captured = _capture_repo(ws)
    assert ".agents/instructions.md" in captured  # scaffold is visible in the captured repo
    assert any(k.startswith(".cortex/") for k in captured)
    assert "CLAUDE.md" in captured and "src/server.ts" in captured  # scaffold + the harness's app code


def test_raw_tool_home_is_not_captured_or_mirrored(tmp_path):
    from gauntlet.livegen.base import _capture_repo
    from gauntlet.livegen.streaming import _scan

    (tmp_path / ".gauntlet-raw-home" / "codex").mkdir(parents=True)
    (tmp_path / ".gauntlet-raw-home" / "codex" / "config.toml").write_text("mcp leak")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export const app = true")

    assert _capture_repo(tmp_path) == {"src/app.ts": "export const app = true"}
    assert _scan(tmp_path) == {"src/app.ts": (tmp_path / "src" / "app.ts").stat().st_mtime}


@pytest.mark.parametrize("governance_only", [False, True])
def test_cli_process_starts_after_scaffold_materialization(tmp_path, monkeypatch, governance_only):
    # Codex/Claude/OpenCode load repo instructions/hooks at process startup. The scaffold must therefore
    # exist before the CLI process starts; dynamic reload after launch is not assumed or required.
    _need_template()
    probe = _startup_probe(tmp_path / "probe")
    out = tmp_path / f"record-{governance_only}.json"
    monkeypatch.setenv("PROBE_OUT", str(out))
    monkeypatch.setattr("gauntlet.livegen.base.shutil.which", lambda _n: str(probe))

    result = _StartupProbeCodeGen(_GOVERNED).generate(
        CodeGenRequest(
            prompt="build the app",
            main_file="m.py",
            scaffold=True,
            scaffold_governance_only=governance_only,
        )
    )
    record = json.loads(out.read_text())
    cwd = Path(record["cwd"]).resolve()
    raw_home = cwd / ".gauntlet-raw-home"

    assert result.ok and result.files["m.py"] == "x = 1\n"
    assert all(record["paths"].values())
    assert "PHASE 0" in record["prompt"] and "ADAPT" in record["prompt"]
    assert Path(record["codex_home"]).resolve().is_relative_to(raw_home)
    assert Path(record["claude_config_dir"]).resolve().is_relative_to(raw_home)


def test_seed_scaffold_fails_fast_when_template_missing(monkeypatch):
    # base setup broken -> RAISE; never run the governed arm as a plain harness in a blank dir
    monkeypatch.setattr("gauntlet.bootstrap.template_available", lambda: False)
    from pathlib import Path

    with pytest.raises(HarnessSetupError):
        CodexCodeGen(_GOVERNED)._seed_scaffold(Path("/tmp/does-not-matter"), None)


# ---- generate_repo refuses to fall back ('it makes no sense to continue') -----
def test_generate_repo_refuses_without_template(monkeypatch):
    monkeypatch.setattr("gauntlet.project.synapse_build.synapse_available", lambda: True)
    monkeypatch.setattr("gauntlet.project.synapse_build.template_available", lambda: False)
    with pytest.raises(HarnessSetupError, match="template"):
        generate_repo(load_project_brief(), "cortex", _GOVERNED, iterations=1)


def test_generate_repo_refuses_without_synapse(monkeypatch):
    monkeypatch.setattr("gauntlet.project.synapse_build.synapse_available", lambda: False)
    with pytest.raises(HarnessSetupError, match="Synapse"):
        generate_repo(load_project_brief(), "cortex", _GOVERNED, iterations=1)


# ---- repair prompts focus on app code, not the 1.4k scaffold files -----------
def test_repair_prompt_embeds_app_code_not_the_scaffold():
    _need_template()
    scaffold_key = next(iter(scaffold_paths()))
    files = {scaffold_key: "SECRET SCAFFOLD CONTENT", "src/app.ts": "export const app = 1"}
    prompt = _repair_prompt("brief", {"cart"}, files)
    assert "src/app.ts" in prompt and "export const app = 1" in prompt  # app code is embedded
    assert "SECRET SCAFFOLD CONTENT" not in prompt                      # scaffold contents are not
    assert "scaffold" in prompt.lower()                                 # but its presence is noted


# ---- generative governed arms: governance-only scaffold (no launch hijack) ---
def test_governance_only_scaffold_does_not_hijack_launch_discovery():
    # the generative track is a stdlib `python app.py`; the full Node/TS template would make the sandbox
    # run `npm install` + serve the template instead of the app. Governance-only excludes every build
    # manifest, so discover_launch still picks the harness's python entrypoint.
    _need_template()
    import tempfile
    from pathlib import Path

    from gauntlet.bootstrap import bootstrap_template
    from gauntlet.livegen.base import _capture_repo
    from gauntlet.project.launch import discover_launch

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        n = bootstrap_template(ws, governance_only=True)
        assert n > 0 and (ws / ".agents" / "instructions.md").exists()  # governance laid
        for trigger in ("package.json", "Makefile", "pyproject.toml"):  # build manifests excluded
            assert not (ws / trigger).exists()
        assert not (ws / "frontend").exists() and not (ws / "backend").exists()  # service stack excluded
        (ws / "app.py").write_text("print('serve')")  # the harness's stdlib app
        captured = _capture_repo(ws)
    launch = discover_launch(captured)
    assert launch.manager == "python"  # NOT node — the scaffold didn't drag a package.json in
    assert ".agents/instructions.md" in captured  # governance still present + visible in the repo


def test_governance_subset_is_within_the_full_scaffold_paths():
    # app_files() subtracts scaffold_paths() (the FULL template). Governance-only must be a subset of it,
    # so a governed generative arm's lint/security metrics still exclude every scaffold file it laid.
    _need_template()
    import tempfile
    from pathlib import Path

    from gauntlet.bootstrap import bootstrap_template
    from gauntlet.livegen.base import _capture_repo

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        bootstrap_template(ws, governance_only=True)
        laid = set(_capture_repo(ws))
    assert laid and laid <= scaffold_paths()


def test_scaffold_note_instructs_adaptation_first():
    # 'adapt the template to the project requirements' must be the harness's FIRST instruction.
    from gauntlet.livegen.base import _SCAFFOLD_NOTE

    note = _SCAFFOLD_NOTE.upper()
    assert "PHASE 0" in note and "ADAPT" in note and "PHASE 1" in note


# ---- the live stream collapses a redrawing CLI's repeated frames -------------
def test_cli_line_strips_ansi_and_collapses_redraw_repeats():
    out: list[str] = []
    reporter = ProgressReporter(out.append)
    reporter.cli_line("\x1b[2J\x1b[Hbuilding tsconfig")  # screen-clear + cursor-home + text
    reporter.cli_line("\x1b[2J\x1b[Hbuilding tsconfig")  # an exact redraw frame — suppressed
    reporter.cli_line("building tsconfig")               # same text after strip — still suppressed
    reporter.cli_line("progress 10%\rprogress 90%")      # CR redraw -> only the final segment survives
    reporter.cli_line("done")
    joined = "".join(out)
    assert "\x1b" not in joined                          # no escape codes leak into the stream
    assert sum("building tsconfig" in line for line in out) == 1  # the redraw collapsed to one line
    assert "progress 90%" in joined and "progress 10%" not in joined
    assert "done" in joined
