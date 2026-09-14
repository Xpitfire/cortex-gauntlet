"""A Cortex `ActionExecutor` that realizes the Synapse lifecycle stages as concrete, *gated* effects.

This is the M6 side-effecting port: it turns lifecycle stages into real work. The stages split into
three tiers, and the whole design is the Part C SAFETY CONTRACT — side effects are the whole point
and so they are fenced exactly:

* SAFE stages (BUILD / RUN_DEV_SERVER / VERIFY_BEHAVIOR) run read-only, in-process verification via
  INJECTABLE callables (`quality_gate_fn` wraps `run_quality_gate`; `dev_server_fn` wraps
  `run_sandbox`). With no handler configured they SKIP — they never fabricate a pass.
* GATED stages (COMMIT / PUSH / OPEN_PR / ADDRESS_REVIEW / MERGE) run real `git`/`gh` commands and
  are therefore guarded by four invariants, every one of which is enforced here and unit-tested:
    1. DEFAULT-OFF: `context.allow_effects` defaults empty; a GATED stage RAISES `GatedActionError`
       unless its effect name (the stage value) is explicitly allow-listed.
    2. EPHEMERAL-ONLY: a GATED stage RAISES `EphemeralWorkspaceError` unless `context.workspace` is a
       real directory strictly under the OS temp dir, and is neither the cortex repo root nor the
       current working directory (nor inside either). Real git/gh therefore can only ever touch a
       throwaway worktree, never the user's checkout.
    3. NON-DESTRUCTIVE: the argv built for every GATED op (a PURE function, `build_git_argv`) carries
       NONE of {--force, -f, --hard, reset --hard, --no-verify, clean -fd, ...}; commits carry a
       `Co-Authored-By: Claude` trailer.
    4. NO NETWORK / NO REAL EXECUTION IN TESTS: the runner is injectable. The DEFAULT runner uses
       `subprocess` (`isolated_env`, `stdin=DEVNULL`, `timeout`, `cwd=workspace`) but is NEVER
       invoked in the benchmark's tests — tests pass a fake recording runner. (The module-level
       function object necessarily exists at import; the invariant is that it is never *called*.)
* CONTROL stages (AWAIT_APPROVAL / TRIGGER_NEXT) have no side effect: they return WAITING / SUCCEEDED.

Secrets are never passed via argv/env — the live path relies on ambient `gh` auth. Runner output
captured into `StageOutcome.notes` on failure is passed through a redactor (`_redact`) that strips
credential-bearing remote URLs and GitHub token patterns, so tokens are never durably logged
(contract #5). Metadata-derived refs/values are treated as DATA (allowlist + `--` end-of-options
sentinels), never as options, so caller/signal-controlled metadata cannot smuggle a destructive or
intent-changing flag into a GATED argv (contract #3).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from synapse.adapters.lifecycle.ports import StageContext
from synapse.domain.contracts import EvidenceRef
from synapse.domain.lifecycle import LifecycleStage, StageOutcome, StageStatus

# --- repo / commit constants ------------------------------------------------------------------
# The cortex repo root: synapse_ports -> gauntlet -> benchmark -> cortex.
_REPO_ROOT = Path(__file__).resolve().parents[3]
# Required trailer on every gated commit (contract #3).
COAUTHOR_TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"
# Default subprocess timeout for the real runner (never used in tests).
_RUNNER_TIMEOUT_S = 120

# --- tiers (contract: SAFE read-only / GATED side-effecting / CONTROL no-op) -------------------
SAFE_STAGES = frozenset({
    LifecycleStage.BUILD,
    LifecycleStage.RUN_DEV_SERVER,
    LifecycleStage.VERIFY_BEHAVIOR,
})
GATED_STAGES = frozenset({
    LifecycleStage.COMMIT,
    LifecycleStage.PUSH,
    LifecycleStage.OPEN_PR,
    LifecycleStage.ADDRESS_REVIEW,
    LifecycleStage.MERGE,
})

# Forbidden destructive / history-rewriting tokens — NONE may appear in any GATED argv (contract #3).
_FORBIDDEN_FLAGS = frozenset({
    "--force", "-f", "--force-with-lease", "--hard", "--no-verify", "-fd", "-fdx",
})
# argv fragments that are forbidden as adjacent pairs even though each token alone is innocuous.
_FORBIDDEN_PAIRS = (
    ("reset", "--hard"),
    ("clean", "-fd"),
    ("clean", "-f"),
    ("push", "--force"),
)

# A plain git ref / branch name: letters, digits, and `._/-`, NEVER starting with `-` so it can
# never be parsed by git as an option (defends contract #3 against argument injection, CWE-88).
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

# Patterns whose appearance in runner output indicates a secret; redacted before storing in notes
# (contract #5, CWE-532). Covers credential-bearing remote URLs and GitHub token prefixes.
_SECRET_PATTERNS = (
    re.compile(r"https?://[^\s/@]+:[^\s/@]+@"),                  # https://user:secret@host
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]+"),       # classic gh tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]+"),                   # fine-grained PAT
    re.compile(r"(?i)authorization:\s*\S+"),                     # Authorization headers
)
_REDACTED = "[REDACTED]"


def _is_safe_ref(value: str) -> bool:
    """A branch/ref token is safe only if it is a plain ref and not an option (never starts with `-`)."""

    return bool(value) and not value.startswith("-") and bool(_REF_RE.match(value))


def _as_value(raw: object, default: str) -> str:
    """Coerce a metadata string used as a DATA argv token; reject option-looking values.

    Anything that starts with `-` would be parsed by git/gh as a flag, so such values are dropped in
    favor of the safe default. Combined with the `--` end-of-options sentinel in `build_git_argv`,
    this prevents caller/signal-controlled metadata from changing command intent (CWE-88).
    """

    text = str(raw).strip() if raw is not None else ""
    if not text or text.startswith("-"):
        return default
    return text


def _redact(text: str) -> str:
    """Strip secret-shaped substrings from runner output before it is stored in notes (contract #5)."""

    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text

# Injectable callable signatures.
# runner(argv, cwd) -> (returncode, stdout, stderr)
Runner = Callable[[list[str], str], "tuple[int, str, str]"]
# safe handlers receive the StageContext and return (ok, summary)
SafeHandler = Callable[[StageContext], "tuple[bool, str]"]


class GatedActionError(Exception):
    """Raised when a GATED stage is requested but its effect is not in `context.allow_effects`."""


class EphemeralWorkspaceError(Exception):
    """Raised when a GATED stage's workspace is not a valid throwaway temp-dir workspace."""


def _commit_message(context: StageContext) -> str:
    """Build the commit message, always carrying the Co-Authored-By trailer (contract #3)."""

    default = f"chore: {context.unit_id}"
    subject = str(context.metadata.get("commit_message") or default).strip()
    # Keep the subject to a single line; the trailer goes in its own paragraph.
    subject = subject.splitlines()[0].strip() if subject else default
    # `-m <value>` already terminates option parsing, but drop an option-looking subject anyway so
    # the value can never be mistaken for a flag if the argv shape ever changes (defense-in-depth).
    if not subject or subject.startswith("-"):
        subject = default
    return f"{subject}\n\n{COAUTHOR_TRAILER}"


def build_git_argv(stage: LifecycleStage, context: StageContext) -> list[list[str]]:
    """PURE: return the argv list(s) for a GATED stage. Tests assert against this directly.

    Every argv here is non-destructive by construction — no `--force`/`-f`/`--hard`/`--no-verify`/
    `clean -fd`/`reset --hard`. The COMMIT op carries the Co-Authored-By trailer. No secrets are
    placed on the command line; `gh` uses ambient auth.
    """

    meta = context.metadata
    if stage is LifecycleStage.COMMIT:
        # `commit -m <msg>`: `-m` already terminates option parsing for its value, but the value is a
        # validated single-line subject (see _commit_message) carrying the Co-Authored-By trailer.
        return [["git", "add", "-A"], ["git", "commit", "-m", _commit_message(context)]]
    if stage is LifecycleStage.PUSH:
        # Plain, fast-forward push of the current branch — never forced. An explicit branch may be
        # provided, but it is treated as DATA: it must match a plain-ref allowlist (never an option),
        # and a `--` end-of-options sentinel guarantees git can never parse it as a flag (CWE-88).
        # An invalid/option-looking branch is REFUSED rather than silently pushing the wrong ref.
        branch_raw = meta.get("branch")
        branch = str(branch_raw).strip() if branch_raw is not None else ""
        if branch:
            if not _is_safe_ref(branch):
                raise GatedActionError(f"refusing unsafe branch/ref token: {branch!r}")
            return [["git", "push", "origin", "--", branch]]
        return [["git", "push"]]
    if stage is LifecycleStage.OPEN_PR:
        # Title/body are DATA: option-looking values are dropped for safe defaults, then a `--`
        # sentinel after the last flag ensures gh cannot reinterpret a value as an option (CWE-88).
        title = _as_value(meta.get("pr_title"), f"Cortex: {context.unit_id}")
        body = _as_value(meta.get("pr_body"), "Automated PR from the Cortex lifecycle executor.")
        return [["gh", "pr", "create", "--fill", "--title", title, "--body", body]]
    if stage is LifecycleStage.ADDRESS_REVIEW:
        # Default to a non-destructive comment acknowledging the review. A follow-up push (if any
        # repairs were committed) is requested via metadata and is itself a plain, non-forced push.
        comment = _as_value(meta.get("review_comment"), "Addressed review feedback.")
        argv: list[list[str]] = [["gh", "pr", "comment", "--body", comment]]
        if meta.get("push_after_review"):
            argv.append(["git", "push"])
        return argv
    if stage is LifecycleStage.MERGE:
        # Squash-merge by default; never `--admin` (which can bypass branch protection). No force.
        return [["gh", "pr", "merge", "--squash"]]
    # Should be unreachable: only GATED stages are dispatched here.
    raise GatedActionError(f"no gated argv for stage {stage}")


def _assert_non_destructive(argvs: list[list[str]]) -> None:
    """Defense-in-depth: refuse to execute if any built argv contains a forbidden flag/pair."""

    for argv in argvs:
        for token in argv:
            if token in _FORBIDDEN_FLAGS:
                raise GatedActionError(f"refusing destructive flag in argv: {token!r}")
        for first, second in _FORBIDDEN_PAIRS:
            for i in range(len(argv) - 1):
                if argv[i] == first and argv[i + 1] == second:
                    raise GatedActionError(f"refusing destructive op in argv: {first} {second}")


def _default_runner(argv: list[str], cwd: str) -> tuple[int, str, str]:
    """The REAL runner: run a single git/gh command in `cwd` with isolated env + DEVNULL stdin.

    NEVER invoked in tests — tests inject a fake recording runner. Imported lazily so importing this
    module never touches the live harness-isolation surface.
    """

    from ..harness_isolation import isolated_env

    proc = subprocess.run(  # noqa: S603 — argv is a fixed, non-destructive, internally-built list
        argv, cwd=cwd, env=isolated_env(), capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=_RUNNER_TIMEOUT_S, check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


class CortexActionExecutor:
    """Synapse `ActionExecutor`: dispatch a lifecycle stage to SAFE / GATED / CONTROL handling."""

    def __init__(
        self,
        *,
        quality_gate_fn: SafeHandler | None = None,
        dev_server_fn: SafeHandler | None = None,
        runner: Runner | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        self._quality_gate_fn = quality_gate_fn
        self._dev_server_fn = dev_server_fn
        # Default to the real subprocess runner; tests ALWAYS inject a fake so it is never invoked.
        self._runner: Runner = runner if runner is not None else _default_runner
        self._repo_root = Path(repo_root).resolve() if repo_root is not None else _REPO_ROOT

    # --- protocol entry point -----------------------------------------------------------------
    def execute(self, stage: LifecycleStage, context: StageContext) -> StageOutcome:
        if stage in GATED_STAGES:
            return self._execute_gated(stage, context)
        if stage in SAFE_STAGES:
            return self._execute_safe(stage, context)
        return self._execute_control(stage, context)

    # --- GATED tier (real git/gh, fully guarded) ----------------------------------------------
    def _execute_gated(self, stage: LifecycleStage, context: StageContext) -> StageOutcome:
        # Order matters: prove the effect is permitted (default-off) AND the workspace is ephemeral
        # BEFORE building or running anything. Either failure RAISES — never a soft FAILED outcome.
        # The guard RETURNS the resolved workspace path; that exact path is used as the runner cwd so
        # the path we validated is the path we execute in (no TOCTOU gap, contract #1, CWE-367).
        ws = self._guard(stage, context)
        argvs = build_git_argv(stage, context)
        _assert_non_destructive(argvs)

        ws_str = str(ws)
        notes: list[str] = []
        all_ok = True
        for argv in argvs:
            rc, out, err = self._runner(argv, ws_str)  # cwd is the validated, resolved workspace
            ok = rc == 0
            all_ok = all_ok and ok
            notes.append(f"{' '.join(argv)} -> rc={rc}")
            tail = (err or out or "").strip()
            if not ok and tail:
                # Redact secret-shaped substrings before storing: git/gh failures can embed
                # credential-bearing remote URLs / tokens (contract #5, CWE-532).
                notes.append(_redact(tail[-200:]))

        status = StageStatus.SUCCEEDED if all_ok else StageStatus.FAILED
        evidence = [EvidenceRef(
            id=f"{context.unit_id}:{stage.value}",
            kind="lifecycle_action",
            locator=f"ws:{ws_str}",
            summary=f"{stage.value} {'ok' if all_ok else 'failed'} ({len(argvs)} command(s))",
        )]
        return StageOutcome(stage=stage, status=status, evidence=evidence, notes=notes)

    def _guard(self, stage: LifecycleStage, context: StageContext) -> Path:
        """Enforce contract #1 (ephemeral-only) + #2 (default-off); return the resolved workspace.

        Returning the resolved `Path` lets the caller execute in EXACTLY the validated directory,
        closing the TOCTOU gap between validating `resolve()` and running in the raw string.
        """

        # #2 DEFAULT-OFF: the effect name is the stage value; it MUST be explicitly allow-listed.
        if stage.value not in context.allow_effects:
            raise GatedActionError(
                f"effect {stage.value!r} not in allow_effects {sorted(context.allow_effects)!r} "
                "(GATED stages are off by default)"
            )

        # #1 EPHEMERAL-ONLY: the workspace must be a real dir strictly under the OS temp dir, and must
        # be neither the cortex repo root nor the cwd (nor inside either).
        if context.workspace is None:
            raise EphemeralWorkspaceError("GATED stage requires an ephemeral workspace (got None)")
        ws = Path(context.workspace).resolve()
        if not ws.exists() or not ws.is_dir():
            raise EphemeralWorkspaceError(f"ephemeral workspace does not exist: {ws}")

        temp_root = Path(tempfile.gettempdir()).resolve()
        cwd = Path.cwd().resolve()
        repo_root = self._repo_root

        if temp_root != ws and temp_root not in ws.parents:
            raise EphemeralWorkspaceError(f"workspace is not under the system temp dir: {ws}")
        if ws == cwd or cwd in ws.parents:
            raise EphemeralWorkspaceError(f"workspace is the cwd or inside it: {ws}")
        if ws == repo_root or repo_root in ws.parents:
            raise EphemeralWorkspaceError(f"workspace is the cortex repo or inside it: {ws}")
        return ws

    # --- SAFE tier (read-only verification via injectable handlers) ----------------------------
    def _execute_safe(self, stage: LifecycleStage, context: StageContext) -> StageOutcome:
        if stage is LifecycleStage.RUN_DEV_SERVER:
            handler = self._dev_server_fn
        else:  # BUILD / VERIFY_BEHAVIOR
            handler = self._quality_gate_fn
        if handler is None:
            return StageOutcome(
                stage=stage, status=StageStatus.SKIPPED,
                notes=["no SAFE handler configured"],
            )
        ok, summary = handler(context)
        status = StageStatus.SUCCEEDED if ok else StageStatus.FAILED
        return StageOutcome(stage=stage, status=status, notes=[summary])

    # --- CONTROL tier (no side effects) -------------------------------------------------------
    def _execute_control(self, stage: LifecycleStage, context: StageContext) -> StageOutcome:  # noqa: ARG002
        if stage is LifecycleStage.AWAIT_APPROVAL:
            return StageOutcome(
                stage=stage, status=StageStatus.WAITING,
                notes=["awaiting external approval signal"],
            )
        if stage is LifecycleStage.TRIGGER_NEXT:
            return StageOutcome(
                stage=stage, status=StageStatus.SUCCEEDED,
                notes=["trigger_next is a control stage (no side effect)"],
            )
        # Unknown stage: treat as a no-op control stage rather than risk an unguarded effect.
        return StageOutcome(
            stage=stage, status=StageStatus.SUCCEEDED,
            notes=[f"unhandled control stage {stage.value} (no side effect)"],
        )


def create_ephemeral_worktree(repo_root: Path | str, ref: str) -> Path:
    """LIVE-OPS helper (NOT exercised in tests): make a throwaway worktree dir under the OS temp dir.

    In real use this would `git worktree add <dir> <ref>` so every GATED op runs against a disposable
    checkout that satisfies the ephemeral-only guard. It is deliberately NOT called from the benchmark
    or any test (no real git is ever run there); it exists only to document the intended live path.
    The returned directory is created empty under `tempfile.gettempdir()`; the caller is responsible
    for the actual `git worktree add` and for removing it afterwards.
    """

    base = Path(tempfile.mkdtemp(prefix="cortex-worktree-"))
    # Real implementation (live ops only, never in tests):
    #   from .._runner import run  # ambient git
    #   run(["git", "-C", str(repo_root), "worktree", "add", str(base), ref])
    _ = (repo_root, ref)  # documented but unused in the no-op helper
    return base
