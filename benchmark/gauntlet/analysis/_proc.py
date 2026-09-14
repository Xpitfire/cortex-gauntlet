"""`subprocess.run` with a retry on the transient launch failures a long-running, multithreaded
process hits during fork/exec.

CPython raises `ValueError: bad value(s) in fds_to_keep` (and transient `OSError`: EMFILE/EAGAIN) when
the file-descriptor table is momentarily racing while a child is being spawned. The benchmark launches
many short-lived analyzers (Semgrep / Bandit / ruff / mypy / pytest) from the TUI's worker thread while
codegen/build pipe-reader threads churn fds — so a momentary race must self-heal via a retry, never
escape and zero a scored cell. On a persistent failure we raise `subprocess.SubprocessError`, which the
analysis call sites already catch and degrade gracefully (TimeoutExpired, a SubprocessError subclass,
propagates unchanged so real timeouts are handled as before).
"""

from __future__ import annotations

import errno
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

_FD_RACE = "fds_to_keep"  # the substring in CPython's ValueError for the threaded fork/exec fd race
# only genuine transient resource-exhaustion errnos count as the race; any OTHER OSError is a real error
# and must surface, not be retried/swallowed as "transient"
_FD_RACE_ERRNOS = frozenset({errno.EMFILE, errno.ENFILE, errno.EAGAIN})
_T = TypeVar("_T")

# Serialize fork/exec across threads: CPython's subprocess is NOT thread-safe across simultaneous spawns
# with the default close_fds=True. The lock is held ONLY across Popen.__init__ (process creation, ~ms),
# never the wait, so spawns are mutually exclusive while subprocesses still run concurrently.
_FORK_LOCK = threading.Lock()
_fork_lock_installed = False


def install_fork_lock() -> None:
    """Wrap `subprocess.Popen.__init__` so every fork/exec in this process is serialized — the ROOT fix
    for `bad value(s) in fds_to_keep`. The benchmark spawns analyzers (semgrep/ruff/mypy/pytest/node/
    docker) from many cell threads at once; while one thread builds + validates its `fds_to_keep` and
    forks, another thread opening/closing fds corrupts the shared fd view, so the race fires continuously
    and a retry can't win it. One lock around creation makes the fork/exec window mutually exclusive.
    Covers library-internal forks too (torch/transformers, the Docker SDK) since they also go through
    `Popen`. Idempotent; call once at process start, before any worker thread spawns a subprocess."""

    global _fork_lock_installed
    if _fork_lock_installed:
        return
    _orig_init = subprocess.Popen.__init__

    def _locked_init(self, *args, **kwargs):
        with _FORK_LOCK:  # released as soon as the child is forked/exec'd — the caller waits unlocked
            _orig_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _locked_init  # type: ignore[method-assign]
    _fork_lock_installed = True


def is_fd_race(exc: BaseException) -> bool:
    """True if `exc` is the transient threaded fork/exec fd-table race — safe to retry, not a real bug.

    Recognises the three shapes the race surfaces as: CPython's `ValueError: bad value(s) in fds_to_keep`
    (raw, from a Popen our wrappers don't own — e.g. a library-internal fork in torch/transformers), the
    EMFILE/EAGAIN `OSError` on a momentarily-exhausted fd table, and the wrapped `SubprocessError` that
    `run()` raises once its own retries are exhausted. A `TimeoutExpired` (also a SubprocessError) is a
    real timeout, NOT the race, so it is excluded."""

    if isinstance(exc, ValueError):
        return _FD_RACE in str(exc)
    if isinstance(exc, subprocess.SubprocessError):
        return "transient fd race" in str(exc)  # only the exhaustion message run() raises below
    return isinstance(exc, OSError) and exc.errno in _FD_RACE_ERRNOS


def run(argv: Sequence[str], *, retries: int = 3, backoff: float = 0.25,
        **kwargs) -> subprocess.CompletedProcess:
    """Drop-in `subprocess.run` that retries the transient fd-table race before giving up."""

    last: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(argv, **kwargs)
        # ValueError/OSError only: a TimeoutExpired (SubprocessError) is a real timeout and propagates
        except (ValueError, OSError) as exc:
            if not is_fd_race(exc):  # an unrelated ValueError is a real bug — never swallow it
                raise
            last = exc
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    raise subprocess.SubprocessError(
        f"subprocess launch failed after {retries + 1} attempts (transient fd race): {last}")


def retry_fd_race(fn: Callable[[], _T], *, retries: int = 3, backoff: float = 0.25,
                  on_retry: Callable[[int, BaseException], None] | None = None) -> _T:
    """Call `fn()`, retrying ONLY the transient fd-table race before giving up; re-raise anything else
    at once. For wrapping work whose subprocess fork is NOT ours to route through `run()` — a
    library-internal `Popen` (torch/transformers in the VERTEX embedder, the Docker SDK) or a whole
    scoring pass. On persistent failure the last race error is re-raised so the caller's existing
    degrade path runs exactly as before (just after self-healing the common momentary case)."""

    last: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — re-raised immediately unless it's the transient race
            if not is_fd_race(exc):
                raise
            last = exc
            if on_retry is not None:
                on_retry(attempt, exc)
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    assert last is not None
    raise last
