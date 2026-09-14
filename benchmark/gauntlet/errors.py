"""Shared benchmark exceptions."""

from __future__ import annotations


class HarnessTimeout(RuntimeError):
    """A harness CLI exceeded its wall-clock budget. NOT a refusal or a compliance and NOT an error:
    the cell is recorded as SKIPPED, excluded from the pass/fail denominator, and surfaced separately
    so a slow run never distorts the headline numbers."""


class AssetUnsupported(RuntimeError):
    """The harness cannot actually RECEIVE this case's asset (e.g. audio on a non-audio CLI, or an
    image on a CLI with no image input). Scoring it would be meaningless — the model never saw the
    payload — so the cell is SKIPPED (excluded from the %) rather than counted as a refusal."""


class HarnessSetupError(RuntimeError):
    """A governed (Cortex-wrapped) arm could not be set up as configured — the Synapse library is not
    importable, or the Cortex project template is missing / extracted nothing. The arm is recorded as
    not-executed WITH this reason; it is NEVER silently downgraded to a plain (ungoverned) harness,
    which would report a raw result under a 'Cortex' label. 'It makes no sense to continue if the base
    setup is not properly done' — so the governed arm stops here rather than falling back."""


class RedTeamError(RuntimeError):
    """The configured adaptive red-team backend could not produce the next user turn — the generator CLI
    is unreachable, returned unparseable output, or declined to author the message even after retries.
    Like HarnessSetupError, it is NEVER silently swapped for a different (unconfigured) backend: a run
    asked for `--red-team claude` must not quietly emit heuristic turns under that label. A missing CLI
    fails fast at build time; a per-turn generation failure ends that one adaptive attack path."""


class EvaluationUnavailable(RuntimeError):
    """Required benchmark infrastructure could not produce an evaluable signal."""


class SandboxUnavailable(EvaluationUnavailable):
    """The sealed Docker execution boundary is unavailable.

    Untrusted generated code must never fall back to host execution or be scored as a candidate
    failure when the benchmark infrastructure cannot confine it.
    """


class SemanticJudgeUnavailable(EvaluationUnavailable):
    """A required semantic judge did not produce a verdict.

    A judge outage is unevaluable benchmark infrastructure, not evidence that an attack was blocked.
    """
