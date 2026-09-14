"""Data model for live code generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CodeGenRequest:
    prompt: str
    language: str = "python"
    main_file: str = "solution.py"
    timeout_s: int = 300  # legacy hard cap; streaming codegen uses inactivity_s/ceiling_s instead
    capture_repo: bool = False  # capture the WHOLE workspace tree (Track P full-stack repo), not one language
    # Streaming watchdog (live Track P/G): terminate on INACTIVITY, not a fixed cap — a healthy long
    # build survives while a hung one is killed quickly. A coding agent can run for hours on a hard repo.
    inactivity_s: int = 1200  # no stdout AND no new files for this long -> stuck (terminate, salvage)
    ceiling_s: int = 14400  # absolute safety cap (4 h)
    reporter: object | None = None  # a ProgressReporter for live narration (None = quiet)
    mirror_dir: str | None = None  # live-mirror the temp workspace here so the repo is browsable on disk
    # Governed (Cortex-wrapped) arms only: seed the workspace with the Cortex project template
    # (.agents/ instructions + hooks, .cortex/, quality gates, adapters) BEFORE the CLI runs, so the
    # harness builds INSIDE the scaffold — the wrapping under test. Raw arms keep a blank workspace.
    scaffold: bool = False
    # Lay only the governance core (no full Node/TS service stack) — for non-full-stack tasks like the
    # generative track's stdlib `python app.py`, so the scaffold never hijacks launch discovery.
    scaffold_governance_only: bool = False


@dataclass(slots=True)
class CodeGenResult:
    backend: str
    main_code: str
    files: dict[str, str] = field(default_factory=dict)
    tokens: int = 0
    wall_ms: int = 0
    ok: bool = False
    error: str = ""
    rate_limited: bool = False  # the CLI hit a provider rate limit (pause/resume, never a task failure)
    timed_out: bool = False  # the CLI went silent (stuck) — partial files kept so the loop can salvage/retry
