"""Discover how to install / build / serve a candidate repo of unknown structure.

The Track P prompt is open-ended, so the harness chooses the stack + layout. The sandbox must
recover a runnable launch plan from the captured file tree: detect the package manager (pnpm/npm/
yarn) and Python entrypoints, read `package.json` scripts (build/start/preview/dev) or a Makefile
target, and pick a serve command bound to `$PORT`. Pure + deterministic so it is unit-testable
without a container.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PORT = 8080  # the sandbox binds the app here; serve commands receive it via $PORT
_SKIP_DIRS = frozenset({
    ".gauntlet-raw-home", "node_modules", ".git", ".hg", ".deepsec", ".agents", ".codex",
    ".claude", ".opencode", ".github", ".cortex", ".husky",
})
# Matches explicit script port flags such as `--port 3000` or `-p 5173`.
_PORT_FLAG = re.compile(r"(?:--port|-p)\s+(\d{2,5})")


@dataclass(slots=True)
class LaunchPlan:
    manager: str  # "pnpm" | "npm" | "yarn" | "python" | "unknown"
    install: list[str] = field(default_factory=list)
    build: list[str] = field(default_factory=list)
    serve: list[str] = field(default_factory=list)
    port: int = PORT
    workdir: str = "."  # dir (relative to repo root) holding the app to serve
    note: str = ""

    @property
    def serveable(self) -> bool:
        return bool(self.serve)


def _skip(path: str) -> bool:
    return bool(_SKIP_DIRS.intersection(path.split("/")))


def _best_package_json(files: dict[str, str]) -> tuple[str, dict] | None:
    candidates: list[tuple[tuple[bool, bool, int], str, dict]] = []
    for path in (p for p in files if p.endswith("package.json") and not _skip(p)):
        try:
            data = json.loads(files[path])
        except json.JSONDecodeError:
            continue
        scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
        candidates.append(((not bool(_serve_script(scripts)), "build" not in scripts, path.count("/")),
                           path, data))
    if candidates:
        _, path, data = min(candidates)
        return path, data
    return None


def _node_manager(files: dict[str, str], workdir: str) -> str:
    prefix = "" if workdir == "." else f"{workdir.rstrip('/')}/"
    if f"{prefix}pnpm-lock.yaml" in files or (workdir != "." and "pnpm-lock.yaml" in files):
        return "pnpm"
    if f"{prefix}yarn.lock" in files or (workdir != "." and "yarn.lock" in files):
        return "yarn"
    return "npm"


def _serve_script(scripts: dict[str, str]) -> str | None:
    for name in ("start", "preview", "serve", "dev"):  # preference order for a served build
        if name in scripts:
            return name
    return None


def _script_port(script: str | None) -> int:
    match = _PORT_FLAG.search(script or "")
    return int(match.group(1)) if match else PORT


def _makefile_target(files: dict[str, str]) -> str | None:
    mk = next((files[p] for p in files if p.endswith("Makefile") and not _skip(p)), None)
    if not mk:
        return None
    for target in ("serve", "start", "run", "dev"):
        if re.search(rf"^{target}:", mk, re.MULTILINE):
            return target
    return None


def _python_entry(files: dict[str, str]) -> str | None:
    for name in ("app.py", "main.py", "server.py", "manage.py", "wsgi.py"):
        match = next((p for p in files if p.split("/")[-1] == name and not _skip(p)), None)
        if match:
            return match
    return None


def discover_launch(files: dict[str, str]) -> LaunchPlan:
    """Best-effort runnable plan from a captured repo tree (Node-first, then Makefile, then Python)."""

    pkg = _best_package_json(files)
    if pkg is not None:
        path, data = pkg
        workdir = path.rsplit("package.json", 1)[0].rstrip("/") or "."
        mgr = _node_manager(files, workdir)
        scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
        install = {"pnpm": ["pnpm", "install"], "yarn": ["yarn", "install"]}.get(mgr, ["npm", "install"])
        build = [mgr, "run", "build"] if "build" in scripts else []
        serve_name = _serve_script(scripts)
        serve = [mgr, "run", serve_name] if serve_name else []
        return LaunchPlan(mgr, install, build, serve, _script_port(scripts.get(serve_name)), workdir,
                          note=f"node/{mgr}; serve via '{serve_name}'" if serve_name else "node; no serve script")

    target = _makefile_target(files)
    if target is not None:
        return LaunchPlan("unknown", [], [], ["make", target], PORT, ".", note=f"Makefile '{target}'")

    entry = _python_entry(files)
    if entry is not None:
        install = ["pip", "install", "-r", "requirements.txt"] if any(
            p.endswith("requirements.txt") for p in files) else []
        return LaunchPlan("python", install, [], ["python3", entry], PORT,
                          entry.rsplit("/", 1)[0] if "/" in entry else ".", note=f"python entry '{entry}'")

    return LaunchPlan("unknown", note="no runnable launch plan discovered")
