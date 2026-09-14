"""Run a subprocess under an INACTIVITY watchdog instead of a fixed wall-clock cap.

A coding-agent CLI may legitimately work for hours on a hard task; a hung one produces nothing. So
rather than a hard timeout that kills healthy long builds and still wastes the whole window on a hang,
we watch for *activity* — new stdout/stderr OR new/changed files in the workspace — and terminate only
after `inactivity_s` of total silence (or an absolute `ceiling_s` safety cap). Output lines, file
changes, and idle ticks are forwarded to callbacks so the caller can narrate live progress and mirror
the growing workspace to a browsable on-disk dir. Killing tears down the whole process group so the
CLI's children die with it.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# directories never counted as "activity" or mirrored — deps/caches/build output churn on their own
WATCH_SKIP_DIRS = frozenset({
    "node_modules", ".git", ".hg", "dist", "build", ".next", ".nuxt", ".svelte-kit", ".cache",
    ".turbo", ".parcel-cache", "coverage", ".pnpm-store", ".venv", "venv", "__pycache__",
    ".ruff_cache", ".pytest_cache", ".mypy_cache", ".gauntlet-raw-home",
})

DEFAULT_INACTIVITY_S = 1200   # 20 min of total silence (no output AND no file writes) -> stuck
DEFAULT_CEILING_S = 14400     # 4 h absolute safety cap
_POLL_S = 3.0                 # watchdog / heartbeat tick
_MAX_MIRROR_BYTES = 512 * 1024  # skip oversized/binary blobs when mirroring the live workspace


@dataclass(slots=True)
class StreamResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    stuck: bool = False       # killed by the inactivity watchdog (went silent)
    exceeded: bool = False    # killed by the absolute ceiling


def _scan(root: Path | None) -> dict[str, float]:
    """rel-path -> mtime for source files under `root` (skips deps/caches). {} when root is None."""

    if root is None:
        return {}
    out: dict[str, float] = {}
    try:
        for path in root.rglob("*"):
            if not path.is_file() or WATCH_SKIP_DIRS.intersection(path.parts):
                continue
            try:
                out[str(path.relative_to(root))] = path.stat().st_mtime
            except OSError:
                continue
    except OSError:
        pass
    return out


def _mirror(src: Path, dst: Path, rels: list[str]) -> None:
    """Copy changed source files from the (ephemeral) workspace to a browsable on-disk dir."""

    for rel in rels:
        source = src / rel
        try:
            if source.stat().st_size > _MAX_MIRROR_BYTES:
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except OSError:
            continue


def _terminate(proc: subprocess.Popen) -> None:
    """Kill the whole process group (the CLI may have spawned children), escalating TERM -> KILL."""

    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(sig)
            except (ProcessLookupError, OSError):
                return
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def _spawn(argv: list[str], cwd: Path | str | None, env: dict[str, str] | None) -> subprocess.Popen:
    """Popen with piped stdout/stderr, retrying the transient threaded fork/exec fd race CPython raises
    as `ValueError: bad value(s) in fds_to_keep` (and transient OSError) when the fd table is momentarily
    racing under many concurrent short-lived children."""
    last: BaseException | None = None
    for attempt in range(4):
        try:
            return subprocess.Popen(
                argv, cwd=str(cwd) if cwd is not None else None, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                start_new_session=True,
            )
        except ValueError as exc:
            if "fds_to_keep" not in str(exc):
                raise
            last = exc
        except OSError as exc:  # EMFILE / EAGAIN on a momentarily-exhausted fd table
            last = exc
        time.sleep(0.25 * (attempt + 1))
    raise last if last is not None else RuntimeError("Popen failed")


def run_streamed(
    argv: list[str], *, cwd: Path | str | None = None, env: dict[str, str] | None = None,
    watch_dir: Path | None = None, mirror_dir: Path | None = None,
    inactivity_s: int = DEFAULT_INACTIVITY_S, ceiling_s: int = DEFAULT_CEILING_S,
    poll_s: float = _POLL_S,
    on_output: Callable[[str], None] | None = None,
    on_files: Callable[[list[str]], None] | None = None,
    on_tick: Callable[[float, float, int], None] | None = None,
) -> StreamResult:
    """Run `argv`, streaming output and watching `watch_dir`; terminate on inactivity or the ceiling.

    Callbacks (each wrapped so narration can never break the run):
      on_output(line):  one captured stdout/stderr line (newline stripped).
      on_files(rels):   source files that appeared/changed since the last tick.
      on_tick(idle_s, elapsed_s, n_files):  every poll, for heartbeats / progress.
    """

    out_buf: list[str] = []
    err_buf: list[str] = []
    last_activity = time.monotonic()
    lock = threading.Lock()
    forwarded = [0, 0]  # how many out/err lines already handed to on_output (drained by the poll loop)

    def pump(stream, buf: list[str]) -> None:
        # reader threads ONLY buffer + stamp activity; callbacks fire on the poll-loop thread (below),
        # so on_output/on_files/on_tick — and the caller's emit sink — are never called concurrently.
        nonlocal last_activity
        try:
            for raw in iter(stream.readline, ""):
                with lock:
                    buf.append(raw)
                    last_activity = time.monotonic()
        except (ValueError, OSError):  # the pipe was closed under us during teardown — stop quietly
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def drain_output() -> None:
        if on_output is None:
            return
        with lock:
            fresh = out_buf[forwarded[0]:] + err_buf[forwarded[1]:]
            forwarded[0], forwarded[1] = len(out_buf), len(err_buf)
        for line in fresh:
            try:
                on_output(line.rstrip("\n"))
            except Exception:  # noqa: BLE001 — narration must never break the run
                pass

    proc = _spawn(argv, cwd, env)
    readers = [threading.Thread(target=pump, args=(proc.stdout, out_buf), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, err_buf), daemon=True)]
    for thread in readers:
        thread.start()

    start = time.monotonic()
    seen = _scan(watch_dir)
    if mirror_dir is not None and seen:
        _mirror(watch_dir, mirror_dir, list(seen))
    stuck = exceeded = False
    while True:
        try:
            proc.wait(timeout=poll_s)
            done = True
        except subprocess.TimeoutExpired:
            done = False
        now = time.monotonic()
        if watch_dir is not None:  # file writes count as activity even while the CLI is quiet
            current = _scan(watch_dir)
            changed = sorted(rel for rel, mtime in current.items() if seen.get(rel) != mtime)
            if changed:
                with lock:
                    last_activity = now
                if mirror_dir is not None:
                    _mirror(watch_dir, mirror_dir, changed)
                if on_files is not None:
                    try:
                        on_files(changed)
                    except Exception:  # noqa: BLE001
                        pass
            seen = current
        drain_output()  # forward any new CLI lines from this tick (single-threaded narration)
        with lock:
            idle = now - last_activity
        if on_tick is not None:
            try:
                on_tick(idle, now - start, len(seen))
            except Exception:  # noqa: BLE001
                pass
        if done:
            break
        if idle >= inactivity_s:
            stuck = True
            _terminate(proc)
            break
        if now - start >= ceiling_s:
            exceeded = True
            _terminate(proc)
            break

    for thread in readers:
        thread.join(timeout=5)
    drain_output()  # final flush: forward any lines that arrived after the last poll
    for stream in (proc.stdout, proc.stderr):  # bound fd use: close pipes even if a reader lingered
        try:
            if stream is not None and not stream.closed:
                stream.close()
        except OSError:
            pass
    return StreamResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout="".join(out_buf), stderr="".join(err_buf),
        duration_s=time.monotonic() - start, stuck=stuck, exceeded=exceeded,
    )
