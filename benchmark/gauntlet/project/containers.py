"""Keep project candidate apps RUNNING after evaluation, each arm on its own host port, for hands-on
qualitative review. Opt-in via `GAUNTLET_KEEP_CONTAINERS=1` (project track only). Started detached after
the probe, tracked in `<run_dir>/containers.json`, and torn down by `cleanup()` when the TUI closes.

This is review-only convenience, deliberately separate from scoring: the SCORE comes from the hardened,
no-egress probe container (which still runs and is removed); these kept containers are a second, plainly
served copy a human can click through. They are bound to 127.0.0.1 (no LAN exposure).
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from ..analysis import _proc
from .launch import LaunchPlan

_MANIFEST = "containers.json"
_BASE_PORT = 8090
_PREFIX = "gauntlet-keep-"


def keep_enabled() -> bool:
    """Whether to keep project containers alive for qualitative review (opt-in, off by default)."""
    return os.environ.get("GAUNTLET_KEEP_CONTAINERS", "").strip() in ("1", "true", "yes")


def _free_port(preferred: int) -> int:
    """The preferred host port if free, else an OS-assigned free one (so parallel arms don't collide)."""
    for candidate in (preferred, 0):
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", candidate))
                return sock.getsockname()[1]
        except OSError:
            continue
    return preferred


def list_kept(run_dir: Path) -> list[dict]:
    """The recorded kept-alive containers for this run (harness, url, port, container, image)."""
    path = Path(run_dir) / _MANIFEST
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _record(run_dir: Path, rec: dict) -> None:
    recs = [r for r in list_kept(run_dir) if r.get("harness") != rec["harness"]] + [rec]
    (Path(run_dir) / _MANIFEST).write_text(json.dumps(recs, indent=2), encoding="utf-8")


def start(image: str, harness_id: str, launch: LaunchPlan, run_dir: Path) -> dict | None:
    """Start a detached serve-only container from the candidate image on its own host port and record it.
    Returns the record (or None if not serveable / docker refused). Never raises — review convenience."""
    if not launch.serveable or not launch.serve:
        return None
    port = _free_port(_BASE_PORT)
    name = f"{_PREFIX}{Path(run_dir).name}-{harness_id}"[:62]
    _proc.run(["docker", "rm", "-f", name], capture_output=True)  # idempotent reuse of the name
    argv = ["docker", "run", "-d", "--name", name,
            "-p", f"127.0.0.1:{port}:{launch.port}",  # loopback only — never exposed to the LAN
            "--cpus", "1", "--memory", "1g", "--pids-limit", "256",
            "-e", f"PORT={launch.port}", image, "sh", "-lc", " ".join(launch.serve)]
    proc = _proc.run(argv, capture_output=True)
    if getattr(proc, "returncode", 1) != 0:
        return None
    rec = {"harness": harness_id, "url": f"http://127.0.0.1:{port}", "port": port,
           "container": name, "image": image}
    _record(run_dir, rec)
    return rec


def cleanup(run_dir: Path) -> int:
    """Stop+remove every kept container (and its ephemeral image) for this run; clear the manifest."""
    recs = list_kept(run_dir)
    for r in recs:
        if r.get("container"):
            _proc.run(["docker", "rm", "-f", r["container"]], capture_output=True)
        if r.get("image"):
            _proc.run(["docker", "image", "rm", "-f", r["image"]], capture_output=True)
    (Path(run_dir) / _MANIFEST).unlink(missing_ok=True)
    return len(recs)


def cleanup_all() -> int:
    """Safety net for a hard exit: remove EVERY gauntlet-keep-* container on the host."""
    proc = _proc.run(["docker", "ps", "-aq", "--filter", f"name={_PREFIX}"], capture_output=True)
    ids = [x for x in (getattr(proc, "stdout", "") or "").split() if x]
    for cid in ids:
        _proc.run(["docker", "rm", "-f", cid], capture_output=True)
    return len(ids)
