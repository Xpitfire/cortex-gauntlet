"""M6 lifecycle ActionExecutor: the Part C SAFETY CONTRACT, proven hermetically.

NO real git/gh/subprocess/Docker/network is ever executed here: every GATED test injects a FAKE
recording runner, every SAFE test injects a fake handler, and the real subprocess runner is never
constructed. The contract is verified exactly:
  #1 EPHEMERAL-ONLY  — None / cwd-rooted / repo-rooted workspaces RAISE; a temp-dir workspace is ok.
  #2 DEFAULT-OFF     — a GATED stage with empty allow_effects RAISES.
  #3 NON-DESTRUCTIVE — no forbidden flags in any GATED argv; commit carries the Co-Authored-By trailer.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("synapse.adapters.lifecycle.ports")

from gauntlet.synapse_ports import (
    CortexActionExecutor,
    EphemeralWorkspaceError,
    GatedActionError,
    build_git_argv,
)
from gauntlet.synapse_ports.action_executor import _REPO_ROOT, GATED_STAGES, _assert_non_destructive
from synapse.adapters.lifecycle.ports import StageContext
from synapse.domain.lifecycle import LifecycleStage, StageStatus

_FORBIDDEN = {"--force", "-f", "--hard", "--no-verify"}

# Each GATED stage with the effect name it requires in allow_effects.
_GATED_EFFECTS = {
    LifecycleStage.COMMIT: "commit",
    LifecycleStage.PUSH: "push",
    LifecycleStage.OPEN_PR: "open_pr",
    LifecycleStage.ADDRESS_REVIEW: "address_review",
    LifecycleStage.MERGE: "merge",
}


class _RecordingRunner:
    """A FAKE runner that records (argv, cwd) and returns success — NO real subprocess is ever run."""

    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, argv: list[str], cwd: str) -> tuple[int, str, str]:
        self.calls.append((list(argv), cwd))
        return self.rc, "ok", ""


def _ephemeral_ws() -> str:
    """A real directory that is provably under the OS temp dir (the only valid GATED workspace)."""

    return tempfile.mkdtemp(prefix="cortex-test-ws-")


def _ctx(stage: LifecycleStage, *, allow: set[str] | None = None, workspace: str | None = None,
         **metadata: object) -> StageContext:
    return StageContext(
        unit_id="unit-1", stage=stage,
        workspace=workspace, allow_effects=frozenset(allow or set()),
        metadata=metadata,
    )


# --- #2 DEFAULT-OFF ---------------------------------------------------------------------------
def test_gated_default_off_raises():
    ws = _ephemeral_ws()
    ex = CortexActionExecutor(runner=_RecordingRunner())
    # empty allow_effects + a perfectly valid ephemeral workspace → STILL raises (default-off).
    with pytest.raises(GatedActionError):
        ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow=set(), workspace=ws))


@pytest.mark.parametrize("stage", sorted(GATED_STAGES, key=lambda s: s.value))
def test_every_gated_stage_default_off_raises(stage):
    # Contract #2 holds for ALL gated stages, not just COMMIT: empty allow_effects → raise.
    ws = _ephemeral_ws()
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(GatedActionError):
        ex.execute(stage, _ctx(stage, allow=set(), workspace=ws))


@pytest.mark.parametrize("stage", sorted(GATED_STAGES, key=lambda s: s.value))
def test_every_gated_stage_none_workspace_raises(stage):
    # Contract #1 holds for ALL gated stages: allowed effect but no workspace → raise.
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(EphemeralWorkspaceError):
        ex.execute(stage, _ctx(stage, allow={_GATED_EFFECTS[stage]}, workspace=None))


@pytest.mark.parametrize("stage", sorted(GATED_STAGES, key=lambda s: s.value))
def test_every_gated_stage_repo_root_workspace_raises(stage):
    # Contract #1 holds for ALL gated stages: a repo-rooted workspace → raise.
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(EphemeralWorkspaceError):
        ex.execute(stage, _ctx(stage, allow={_GATED_EFFECTS[stage]}, workspace=str(_REPO_ROOT)))


def test_gated_wrong_effect_name_raises():
    ws = _ephemeral_ws()
    ex = CortexActionExecutor(runner=_RecordingRunner())
    # an unrelated effect allow-listed does NOT permit commit.
    with pytest.raises(GatedActionError):
        ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow={"push"}, workspace=ws))


# --- #1 EPHEMERAL-ONLY guard ------------------------------------------------------------------
def test_ephemeral_guard_none_workspace_raises():
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(EphemeralWorkspaceError):
        ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=None))


def test_ephemeral_guard_repo_root_raises():
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(EphemeralWorkspaceError):
        ex.execute(
            LifecycleStage.COMMIT,
            _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=str(_REPO_ROOT)),
        )


def test_ephemeral_guard_cwd_raises():
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(EphemeralWorkspaceError):
        ex.execute(
            LifecycleStage.COMMIT,
            _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=str(Path.cwd())),
        )


def test_ephemeral_guard_nonexistent_temp_path_raises():
    # under the temp dir but not actually created → not a real workspace → raise.
    bogus = str(Path(tempfile.gettempdir()) / "cortex-does-not-exist-xyz")
    ex = CortexActionExecutor(runner=_RecordingRunner())
    with pytest.raises(EphemeralWorkspaceError):
        ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=bogus))


def test_ephemeral_guard_temp_dir_is_allowed():
    ws = _ephemeral_ws()
    runner = _RecordingRunner()
    ex = CortexActionExecutor(runner=runner)
    outcome = ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=ws))
    assert outcome.status is StageStatus.SUCCEEDED  # guard passed → runner ran


# --- #3 NON-DESTRUCTIVE argv (pure function) --------------------------------------------------
@pytest.mark.parametrize("stage", [
    LifecycleStage.COMMIT, LifecycleStage.PUSH, LifecycleStage.OPEN_PR,
    LifecycleStage.MERGE, LifecycleStage.ADDRESS_REVIEW,
])
def test_build_git_argv_has_no_forbidden_flags(stage):
    argvs = build_git_argv(stage, _ctx(stage, push_after_review=True))
    all_tokens = [tok for argv in argvs for tok in argv]
    assert not (_FORBIDDEN & set(all_tokens)), f"forbidden flag in {stage}: {all_tokens}"
    # extra: no history-rewriting pair appears either
    joined = " ".join(all_tokens)
    assert "reset --hard" not in joined
    assert "clean -fd" not in joined


def test_commit_argv_carries_coauthor_trailer():
    argvs = build_git_argv(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT))
    # commit message is the last token of the `git commit -m <msg>` argv
    commit_argv = [a for a in argvs if a[:2] == ["git", "commit"]][0]
    assert "Co-Authored-By:" in commit_argv[-1]
    assert "Claude" in commit_argv[-1]


# --- #3 NON-DESTRUCTIVE: metadata-as-options injection is refused (regression for the blocker) -
@pytest.mark.parametrize("branch", [
    "--mirror", "--delete", "-d", "--all", "--tags", "--prune", ":main", "-f", "--force",
])
def test_push_rejects_option_looking_branch(branch):
    # A branch value that is actually a git option must be REFUSED, not placed in argv (CWE-88).
    with pytest.raises(GatedActionError):
        build_git_argv(LifecycleStage.PUSH, _ctx(LifecycleStage.PUSH, branch=branch))


def test_push_with_safe_branch_uses_end_of_options_sentinel():
    # A legitimate branch is allowed and protected by a `--` end-of-options sentinel so git can never
    # parse it as a flag even if it later looked option-like.
    argvs = build_git_argv(LifecycleStage.PUSH, _ctx(LifecycleStage.PUSH, branch="feature/x_1.0"))
    assert argvs == [["git", "push", "origin", "--", "feature/x_1.0"]]


@pytest.mark.parametrize("field,stage", [
    ("pr_title", LifecycleStage.OPEN_PR),
    ("pr_body", LifecycleStage.OPEN_PR),
    ("review_comment", LifecycleStage.ADDRESS_REVIEW),
    ("commit_message", LifecycleStage.COMMIT),
])
def test_option_looking_gh_metadata_is_not_emitted_verbatim(field, stage):
    # An option-looking metadata value (e.g. '--web') must not become an argv option token; it is
    # dropped for the safe default instead (CWE-88 option injection defense-in-depth).
    argvs = build_git_argv(stage, _ctx(stage, **{field: "--web"}))
    all_tokens = [tok for argv in argvs for tok in argv]
    # The injected value must not survive as a standalone option token after a flag.
    assert "--web" not in all_tokens


def test_assert_non_destructive_raises_on_tampered_argv():
    # The runtime second layer must catch a forbidden flag even if it bypassed build_git_argv.
    with pytest.raises(GatedActionError):
        _assert_non_destructive([["git", "push", "--force"]])
    with pytest.raises(GatedActionError):
        _assert_non_destructive([["git", "reset", "--hard"]])
    with pytest.raises(GatedActionError):
        _assert_non_destructive([["git", "clean", "-fd"]])


# --- GATED happy path uses the FAKE runner only -----------------------------------------------
def test_gated_happy_path_uses_fake_runner_with_ephemeral_cwd():
    ws = _ephemeral_ws()
    runner = _RecordingRunner()
    ex = CortexActionExecutor(runner=runner)
    outcome = ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=ws))

    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.evidence and outcome.evidence[0].kind == "lifecycle_action"
    # the fake runner was called for add + commit, ALWAYS with cwd == the RESOLVED ephemeral
    # workspace (the exact path the guard validated — no TOCTOU between check and use).
    resolved = str(Path(ws).resolve())
    assert runner.calls, "runner must have been invoked"
    for argv, cwd in runner.calls:
        assert cwd == resolved
        assert not (_FORBIDDEN & set(argv))


def test_gated_failure_marks_failed_not_raise():
    ws = _ephemeral_ws()
    runner = _RecordingRunner(rc=1)  # non-zero rc → FAILED outcome, but no raise (guard already passed)
    ex = CortexActionExecutor(runner=runner)
    outcome = ex.execute(LifecycleStage.PUSH, _ctx(LifecycleStage.PUSH, allow={"push"}, workspace=ws))
    assert outcome.status is StageStatus.FAILED


class _SecretLeakingRunner:
    """A FAKE runner whose stderr embeds a credential URL + token, to prove notes are redacted."""

    stderr = (
        "fatal: Authentication failed for "
        "'https://x-access-token:ghp_SECRETTOKEN1234567890@github.com/org/repo.git'"
    )

    def __call__(self, argv, cwd):
        return 1, "", self.stderr


def test_gated_failure_redacts_secrets_in_notes():
    # Contract #5: a failing push whose stderr carries a token must NOT leak the token into notes.
    ws = _ephemeral_ws()
    ex = CortexActionExecutor(runner=_SecretLeakingRunner())
    outcome = ex.execute(LifecycleStage.PUSH, _ctx(LifecycleStage.PUSH, allow={"push"}, workspace=ws))
    assert outcome.status is StageStatus.FAILED
    joined = " ".join(outcome.notes)
    assert "ghp_SECRETTOKEN1234567890" not in joined
    assert "x-access-token:" not in joined
    assert "[REDACTED]" in joined  # the redactor actually fired


def test_gated_runner_cwd_is_resolved_path_no_toctou(tmp_path):
    # Contract #1 / CWE-367: the runner must execute in the RESOLVED path that the guard validated,
    # not the raw (possibly symlinked) context.workspace string. Point a symlink under the temp dir
    # at a real temp target; the runner must receive the resolved real target, not the symlink.
    real = Path(tempfile.mkdtemp(prefix="cortex-real-ws-"))
    link = Path(tempfile.gettempdir()) / f"cortex-link-{real.name}"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(real, target_is_directory=True)
    try:
        runner = _RecordingRunner()
        ex = CortexActionExecutor(runner=runner)
        ex.execute(
            LifecycleStage.COMMIT,
            _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=str(link)),
        )
        assert runner.calls
        for _argv, cwd in runner.calls:
            # The cwd handed to the runner is the resolved real dir, never the live symlink path.
            assert Path(cwd) == real.resolve()
            assert cwd != str(link)
    finally:
        link.unlink()


def test_default_real_runner_never_invoked_when_fake_injected(monkeypatch):
    # Make the real runner explode if it is EVER called; the injected fake must shield us from it.
    import gauntlet.synapse_ports.action_executor as mod

    def _boom(argv, cwd):
        raise AssertionError("the real subprocess runner must never run in tests")

    monkeypatch.setattr(mod, "_default_runner", _boom)
    ws = _ephemeral_ws()
    runner = _RecordingRunner()
    ex = CortexActionExecutor(runner=runner)  # fake injected
    ex.execute(LifecycleStage.COMMIT, _ctx(LifecycleStage.COMMIT, allow={"commit"}, workspace=ws))
    assert runner.calls  # only the fake ran


# --- SAFE tier --------------------------------------------------------------------------------
def test_safe_stage_with_handler_succeeds():
    ex = CortexActionExecutor(quality_gate_fn=lambda ctx: (True, "gate ok"))
    outcome = ex.execute(LifecycleStage.VERIFY_BEHAVIOR, _ctx(LifecycleStage.VERIFY_BEHAVIOR))
    assert outcome.status is StageStatus.SUCCEEDED
    assert "gate ok" in outcome.notes


def test_safe_stage_handler_fail_is_failed():
    ex = CortexActionExecutor(quality_gate_fn=lambda ctx: (False, "gate FAIL"))
    outcome = ex.execute(LifecycleStage.BUILD, _ctx(LifecycleStage.BUILD))
    assert outcome.status is StageStatus.FAILED


def test_safe_stage_without_handler_is_skipped():
    ex = CortexActionExecutor()  # no handlers, no runner needed
    outcome = ex.execute(LifecycleStage.VERIFY_BEHAVIOR, _ctx(LifecycleStage.VERIFY_BEHAVIOR))
    assert outcome.status is StageStatus.SKIPPED


def test_run_dev_server_dispatches_to_dev_handler():
    ex = CortexActionExecutor(dev_server_fn=lambda ctx: (True, "served"))
    outcome = ex.execute(LifecycleStage.RUN_DEV_SERVER, _ctx(LifecycleStage.RUN_DEV_SERVER))
    assert outcome.status is StageStatus.SUCCEEDED
    assert "served" in outcome.notes


# --- CONTROL tier -----------------------------------------------------------------------------
def test_await_approval_is_waiting_no_effect():
    ex = CortexActionExecutor(runner=_RecordingRunner())
    outcome = ex.execute(LifecycleStage.AWAIT_APPROVAL, _ctx(LifecycleStage.AWAIT_APPROVAL))
    assert outcome.status is StageStatus.WAITING


def test_trigger_next_is_succeeded_no_effect():
    runner = _RecordingRunner()
    ex = CortexActionExecutor(runner=runner)
    outcome = ex.execute(LifecycleStage.TRIGGER_NEXT, _ctx(LifecycleStage.TRIGGER_NEXT))
    assert outcome.status is StageStatus.SUCCEEDED
    assert not runner.calls  # control stage runs NO commands
