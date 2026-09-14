"""Bootstrap a workspace from the Cortex project template — the Cortex arm's starting advantage.

A Cortex(+Synapse) run begins not from a blank directory but from the extracted Cortex template
(`.template-cache/project-template.tar.gz`): engineering instructions, dto/repository/service exemplars,
quality-gate Make targets, verification hooks, and subagent roles. Raw codex/Claude arms get a blank
workspace. This module just materializes that template into a workspace; the harness then adapts the
generic scaffold to the task's requirements and drives them to completion under the Synapse loop.
"""

from __future__ import annotations

import tarfile
from functools import lru_cache
from pathlib import Path

from .paths import ROOT

# repo_root/.template-cache/project-template.tar.gz (ROOT is benchmark/)
TEMPLATE_ARCHIVE = ROOT.parent / ".template-cache" / "project-template.tar.gz"


@lru_cache(maxsize=1)
def _archive() -> Path:
    # Prefer the committed cache for a hermetic, DETERMINISTIC benchmark run — no bash/git subprocess and
    # no archive rebuild mid-run (update the template via the sync script + re-commit .template-cache).
    # Only when the cache is absent (e.g. a packaged install) fall back to the shared cortex_cli resolver
    # (explicit/env/checkout-sync). The broadened except also covers a sync attempt that dies on a host
    # without bash/git (FileNotFoundError is an OSError, NOT a ScaffoldError) instead of propagating.
    if TEMPLATE_ARCHIVE.is_file():
        return TEMPLATE_ARCHIVE
    try:
        from cortex_cli.scaffold import ScaffoldError, locate_archive
    except ModuleNotFoundError as exc:
        if exc.name not in {"cortex_cli", "cortex_cli.scaffold"}:
            raise
        return TEMPLATE_ARCHIVE
    try:
        return locate_archive()
    except (ScaffoldError, OSError):
        return TEMPLATE_ARCHIVE


def template_available() -> bool:
    return _archive().exists()


def _rel(name: str) -> str:
    """Tar members are stored as `./path`; the captured-repo keys are `path` — normalize to the latter."""
    return name[2:] if name.startswith("./") else name


# The Cortex governance core: instructions, hooks, rules, scripts, examples, quality-gate fragments and
# the tool adapters — the project-AGNOSTIC managed environment. Laid for arms whose task is NOT a full
# Node/TS app (e.g. the generative track's stdlib `python app.py`), where dragging in the template's
# whole Node+FastAPI service stack would (a) make `discover_launch` pick a heavy `npm install`/serve over
# the real entrypoint and (b) pollute the harness's lint/security metrics with the scaffold's own code.
_GOVERNANCE_PREFIXES = (".agents/", ".cortex/", ".claude/", ".codex/", ".opencode/", ".github/", ".husky/")
_GOVERNANCE_ROOT_FILES = frozenset({
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", "opencode.json", ".mcp.json.example",
    ".gitignore", ".editorconfig", ".node-version", ".nvmrc", ".python-version",
})
# basenames `discover_launch` keys off — excluded from the governance subset so the scaffold never
# hijacks the candidate's build/serve away from the harness's own entrypoint.
_LAUNCH_TRIGGERS = frozenset({
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Makefile",
    "pyproject.toml", "requirements.txt", "app.py", "main.py", "server.py", "manage.py", "wsgi.py",
})
_RUNTIME_PREFIXES = (".gauntlet-raw-home/",)
_RUNTIME_FILES = frozenset({".DS_Store"})


def _is_governance(rel: str) -> bool:
    base = rel.rsplit("/", 1)[-1]
    if base in _LAUNCH_TRIGGERS:
        return False
    return rel.startswith(_GOVERNANCE_PREFIXES) or rel in _GOVERNANCE_ROOT_FILES


def bootstrap_template(workspace: Path, *, governance_only: bool = False) -> int:
    """Extract the Cortex project template into `workspace`; return the number of files written.

    `governance_only` lays just the Cortex governance core (`.agents/` + adapters + `.cortex/`, minus any
    build-manifest that would steer the sandbox's launch discovery) — the managed environment without the
    full Node/TS service stack, for tasks that aren't a full-stack web app."""

    archive = _archive()
    if not archive.exists():
        raise FileNotFoundError(f"template archive not found: {archive}")
    workspace.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        if governance_only:  # file members only — extract() creates their parent dirs
            members = [m for m in members if m.isfile() and _is_governance(_rel(m.name))]
        tar.extractall(workspace, members=members, filter="data")  # tar filter (py3.12+) blocks unsafe paths
    return sum(1 for member in members if member.isfile())


@lru_cache(maxsize=1)
def scaffold_paths() -> frozenset[str]:
    """The workspace-relative paths the Cortex template lays down (`.agents/…`, `.cortex/…`, `CLAUDE.md`,
    `Makefile`, …). The governed loop subtracts these so it credits/repairs only the APP files the
    harness authored — never the generic scaffold (whose own services/docs would otherwise spuriously
    satisfy storefront markers and stall the loop before the real app is built)."""

    archive = _archive()
    if not archive.exists():
        return frozenset()
    with tarfile.open(archive) as tar:
        return frozenset(_rel(m.name) for m in tar.getmembers() if m.isfile())


def app_files(files: dict[str, str]) -> dict[str, str]:
    """`files` minus the Cortex scaffold — the harness-authored app surface (what the loop observes)."""
    scaffold = scaffold_paths()
    return {
        path: content for path, content in files.items()
        if path not in scaffold and path not in _RUNTIME_FILES
        and not path.startswith(_RUNTIME_PREFIXES)
    }
