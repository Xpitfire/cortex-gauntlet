"""Cortex-side ports that adapt the benchmark to Synapse's lifecycle + signal adapters (M5/M6).

M5 — `CortexReviewerJudge` plugs into the real Synapse `Orchestrator` as a text `CompletionJudge`:
it runs a READ-ONLY second CLI pass of the SAME provider over the current generation, parses its
JSON review, and turns it into a `JudgeVerdict` (plus repair comments). The reviewer is read-only by
construction and NEVER sees the hidden tests or reference solutions — only requirement id + text.

M6 — `CortexActionExecutor` realizes the Synapse lifecycle stages as concrete effects under the Part
C SAFETY CONTRACT (default-off, ephemeral-only, non-destructive, no-network-in-tests), and the
`FileSignalSource` / `GhSignalSource` realize the `SignalSource` protocol (file fixtures in the
benchmark; the gh live path is GATED OFF by default).
"""

from .action_executor import (
    COAUTHOR_TRAILER,
    GATED_STAGES,
    SAFE_STAGES,
    CortexActionExecutor,
    EphemeralWorkspaceError,
    GatedActionError,
    build_git_argv,
    create_ephemeral_worktree,
)
from .reviewer_judge import (
    CortexReviewerJudge,
    ReviewReport,
    build_reviewer,
    format_review_prompt,
    parse_review_reply,
    run_cli_review,
)
from .signal_source import FileSignalSource, GhSignalSource

__all__ = [
    "COAUTHOR_TRAILER",
    "GATED_STAGES",
    "SAFE_STAGES",
    "CortexActionExecutor",
    "CortexReviewerJudge",
    "EphemeralWorkspaceError",
    "FileSignalSource",
    "GatedActionError",
    "GhSignalSource",
    "ReviewReport",
    "build_git_argv",
    "build_reviewer",
    "create_ephemeral_worktree",
    "format_review_prompt",
    "parse_review_reply",
    "run_cli_review",
]
