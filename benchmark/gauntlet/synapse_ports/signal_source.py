"""Cortex `SignalSource` ports: inbound external signals for the Synapse scheduler.

Two implementations realize the same Synapse `SignalSource` protocol:

* `FileSignalSource` is the BENCHMARK path: it reads a local JSON fixture (a list of signal records)
  and returns deterministic `ExternalSignal` objects in file order. It NEVER touches the network. It
  is the only signal source used in the benchmark and in tests.
* `GhSignalSource` is the LIVE-OPS path and is GATED OFF by default: `poll()` returns `[]` and does
  NOT invoke `gh` unless `enabled=True` is passed explicitly. The enabled branch (which would run
  `gh pr view --json comments` via `subprocess`) is NEVER taken in the benchmark or in any test, so
  there is no network access from this module under test.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from synapse.domain.signals import ExternalSignal, SignalCursor, SignalKind

# Map a raw fixture `kind` string onto SignalKind; unknown/missing kinds fall back to CUSTOM.
_KIND_BY_VALUE = {kind.value: kind for kind in SignalKind}


def _to_kind(raw: object) -> SignalKind:
    if isinstance(raw, str):
        return _KIND_BY_VALUE.get(raw, SignalKind.CUSTOM)
    return SignalKind.CUSTOM


class FileSignalSource:
    """A `SignalSource` backed by a local JSON fixture (the benchmark/no-network path).

    The fixture is a JSON list of records, each ``{"id", "kind", "source", "unit_id"?, "payload"?}``.
    Records are returned in file order (deterministic). Optional fields are tolerated. A missing or
    empty/invalid file yields ``[]``.

    Cursor handling: as a convenience this skips records whose ``id`` is already in
    ``cursor.seen_ids`` (idempotency belongs to the scheduler, but skipping seen ids here keeps the
    fixture replayable without duplicate work). It NEVER advances the cursor itself.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def poll(self, cursor: SignalCursor) -> list[ExternalSignal]:
        if not self._path.exists():
            return []
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        if not text.strip():
            return []
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(data, list):
            return []

        signals: list[ExternalSignal] = []
        for record in data:
            if not isinstance(record, dict):
                continue
            sig_id = record.get("id")
            if not isinstance(sig_id, str) or not sig_id:
                continue
            if cursor.has_seen(sig_id):  # convenience: skip already-processed ids (documented)
                continue
            payload = record.get("payload")
            unit_id = record.get("unit_id")
            signals.append(ExternalSignal(
                id=sig_id,
                kind=_to_kind(record.get("kind")),
                source=str(record.get("source") or self._path.name),
                unit_id=unit_id if isinstance(unit_id, str) else None,
                payload=payload if isinstance(payload, dict) else {},
            ))
        return signals


class GhSignalSource:
    """A `SignalSource` for live GitHub PR signals — GATED OFF by default (no network in benchmark).

    With ``enabled=False`` (the default), ``poll()`` returns ``[]`` and never invokes ``gh``. The
    enabled branch is the documented live-ops path: it would run ``gh pr view <pr> --json comments``
    via subprocess (with `isolated_env`/DEVNULL) and map the comments to ``ExternalSignal`` objects.
    That branch is NEVER taken in the benchmark or in tests, so this module performs no network or
    subprocess calls under test.
    """

    def __init__(self, pr: str, *, enabled: bool = False) -> None:
        self._pr = pr
        self._enabled = enabled

    def poll(self, cursor: SignalCursor) -> list[ExternalSignal]:
        if not self._enabled:
            return []  # GATED OFF: no gh, no network. Default path in benchmark + tests.
        return self._poll_live(cursor)

    def _poll_live(self, cursor: SignalCursor) -> list[ExternalSignal]:
        """LIVE-OPS ONLY (never reached in tests): query gh for PR comments and map to signals."""

        from ..harness_isolation import isolated_env

        argv = ["gh", "pr", "view", self._pr, "--json", "comments"]
        try:
            proc = subprocess.run(  # noqa: S603 — fixed argv, ambient gh auth, no secrets on argv
                argv, env=isolated_env(), capture_output=True, text=True,
                stdin=subprocess.DEVNULL, timeout=60, check=False,
            )
        except (subprocess.SubprocessError, OSError):
            return []
        if proc.returncode != 0:
            return []
        try:
            data = json.loads(proc.stdout or "{}")
        except (json.JSONDecodeError, ValueError):
            return []

        signals: list[ExternalSignal] = []
        for comment in data.get("comments") or []:
            if not isinstance(comment, dict):
                continue
            sig_id = str(comment.get("id") or comment.get("url") or "")
            if not sig_id or cursor.has_seen(sig_id):
                continue
            signals.append(ExternalSignal(
                id=sig_id, kind=SignalKind.PR_COMMENT, source=f"gh:pr:{self._pr}",
                payload={"body": comment.get("body", ""), "author": comment.get("author", {})},
            ))
        return signals
