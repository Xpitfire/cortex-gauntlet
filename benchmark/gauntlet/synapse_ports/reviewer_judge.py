"""A read-only Synapse `CompletionJudge` that runs a second CLI review pass over the generation.

The reviewer is the M5 inner loop: after each generation, a SECOND pass of the SAME provider reviews
the current files against the requirements and returns structured comments. Those comments flow back
into the repair prompt, so Cortex iterates toward an approved solution rather than a single shot.

Scoring integrity (HARD): the reviewer is read-only and is shown ONLY requirement id + text — NEVER
the hidden tests (`.test`), nor the reference good/bad code (`.good_code` / `.bad_code`). Any failure
(no files, unparseable reply, CLI missing, unknown provider, subprocess error) DEFAULTS TO NOT APPROVED;
the reviewer never silently approves. Live invocation is best-effort and untested against a live,
authenticated CLI here (mirrors the disclaimer in livegen/adapters.py).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from synapse import CompletionLabel, JudgeContext, JudgeModality, JudgeVerdict

from ..harness_isolation import raw_harness_env
from ..livegen.base import CodeGenAdapter

# tolerate a JSON object embedded in surrounding prose/log lines (the CLI may wrap the verdict)
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(slots=True)
class ReviewReport:
    """Outcome of one read-only review pass: approval + per-requirement comments (no hidden tests)."""

    approved: bool
    comments: list[str] = field(default_factory=list)
    summary: str = ""
    raw: str = ""


ReviewFn = Callable[[dict[str, str], Sequence[Any]], ReviewReport]
FilesProvider = Callable[[], dict[str, str]]


class CortexReviewerJudge:
    """Synapse `CompletionJudge`: review the current files (read-only) → COMPLETE / PARTIAL / POOR."""

    def __init__(
        self,
        review_fn: ReviewFn,
        requirements: Sequence[Any],
        *,
        files_provider: FilesProvider | None = None,
        comments_sink: dict[str, Any] | None = None,
    ) -> None:
        self._review_fn = review_fn
        self._requirements = requirements
        self._files_provider = files_provider
        self._comments_sink = comments_sink

    def assess(self, context: JudgeContext) -> JudgeVerdict:  # noqa: ARG002 — protocol signature
        files = self._files_provider() if self._files_provider else {}
        if not files:  # nothing generated yet → cannot review → not complete (never silent-approve)
            return JudgeVerdict(
                label=CompletionLabel.POOR, modality=JudgeModality.TEXT,
                rationale="no files to review",
            )
        report = self._review_fn(files, self._requirements)
        if self._comments_sink is not None:  # publish the latest comments for the repair prompt
            self._comments_sink["comments"] = list(report.comments)
        label = CompletionLabel.COMPLETE if report.approved else CompletionLabel.PARTIAL
        return JudgeVerdict(
            label=label, modality=JudgeModality.TEXT,
            rationale=(report.summary or "review")[:200],
        )


def _concat(files: dict[str, str]) -> str:
    if len(files) == 1:
        return next(iter(files.values()))
    return "\n\n".join(f"# {path}\n{body}" for path, body in sorted(files.items()))


def format_review_prompt(files: dict[str, str], requirements: Sequence[Any]) -> str:
    """Build the review prompt. CRITICAL: list ONLY requirement .id + .text — NEVER .test / .good_code /
    .bad_code (the hidden ground truth). Ask the reviewer for ONLY a JSON verdict and to NOT write files."""

    req_lines = "\n".join(
        f"- [{getattr(r, 'id', '')}] {getattr(r, 'text', '')}" for r in requirements
    )
    return (
        "You are a senior code reviewer. Review the code below against the requirements. "
        "Do NOT create, write, or edit any files — this is a read-only review.\n\n"
        f"Requirements:\n{req_lines}\n\n"
        "Code under review:\n```\n" + _concat(files) + "\n```\n\n"
        "Return ONLY a single JSON object, no prose, of exactly this form:\n"
        '{"approved": <true|false>, "comments": [{"requirement_id": "<id>", '
        '"severity": "<low|medium|high>", "comment": "<what to fix>"}]}\n'
        "Set \"approved\" true only if every requirement is fully satisfied; otherwise list the gaps "
        "as comments. Output nothing but the JSON object."
    )


def parse_review_reply(stdout: str) -> ReviewReport:
    """Extract the JSON verdict from `stdout` (tolerating surrounding text). On ANY parse failure return
    NOT approved with the raw output captured — never a silent approve."""

    match = _JSON_OBJ.search(stdout or "")
    if not match:
        return ReviewReport(approved=False, summary="unparseable review", raw=(stdout or "")[:300])
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return ReviewReport(approved=False, summary="unparseable review", raw=(stdout or "")[:300])
    if not isinstance(data, dict):
        return ReviewReport(approved=False, summary="unparseable review", raw=(stdout or "")[:300])
    approved = bool(data.get("approved", False))
    comments: list[str] = []
    for c in data.get("comments") or []:
        if isinstance(c, dict):
            rid, sev = c.get("requirement_id", ""), c.get("severity", "")
            text = c.get("comment", "")
            prefix = f"[{rid}/{sev}] " if (rid or sev) else ""
            comments.append(f"{prefix}{text}".strip())
        else:
            comments.append(str(c))
    summary = "approved" if approved else (f"{len(comments)} issue(s) to address" if comments else "not approved")
    return ReviewReport(approved=approved, comments=comments, summary=summary, raw=(stdout or "")[:300])


def _review_argv(codegen: CodeGenAdapter, binary: str, prompt: str) -> list[str] | None:
    """Build the READ-ONLY review argv for the provider behind `codegen`. None for an unknown provider.

    Best-effort, untested against a live CLI here (mirrors livegen/adapters.py). Read-only by design:
    codex runs `-s read-only`; claude is limited to `Read Grep Glob` with NO write tools and NO
    --dangerously-skip-permissions."""

    name = getattr(codegen, "binary_name", "")
    model = getattr(codegen, "model", "")
    if name == "codex":
        argv = [binary, "exec", "-s", "read-only", "--skip-git-repo-check", "--ignore-user-config"]
        if model:
            argv += ["-m", model]
        argv.append(prompt)
        return argv
    if name == "claude":
        # Read-only review: whitelist ONLY Read/Grep/Glob as separate tokens (robust to a list
        # parser), and DELIBERATELY omit --dangerously-skip-permissions — that omission is the
        # primary write guard: any write/edit tool would hit a permission prompt that stdin=DEVNULL
        # can never approve, so it is denied even if the whitelist were malformed.
        argv = [binary, "-p", prompt, "--allowedTools", "Read", "Grep", "Glob"]
        if model:
            argv += ["--model", model]
        return argv
    return None


def run_cli_review(codegen: CodeGenAdapter) -> ReviewFn:
    """Return a `review_fn(files, requirements) -> ReviewReport` that runs a READ-ONLY second CLI pass of
    the SAME provider and parses its reply. Never raises; never silent-approves on any failure."""

    timeout_s = getattr(codegen, "timeout_s", 300)

    def review_fn(files: dict[str, str], requirements: Sequence[Any]) -> ReviewReport:
        name = getattr(codegen, "binary_name", "")
        binary = shutil.which(name) if name else None
        if binary is None:
            return ReviewReport(approved=False, summary=f"reviewer CLI '{name}' not found")
        prompt = format_review_prompt(files, requirements)
        argv = _review_argv(codegen, binary, prompt)
        if argv is None:
            return ReviewReport(approved=False, summary="no reviewer for provider")
        # Defense-in-depth: run the review in a fresh empty temp dir OUTSIDE the repo (mirrors
        # SubprocessCodeGen.generate). The files-under-review are passed in the prompt, so the
        # reviewer needs no real cwd; an isolated empty cwd guarantees its Read/Grep/Glob tools
        # cannot reach the repo or any on-disk artifact even if the hidden-tests-never-on-disk
        # invariant were ever violated. raw_harness_env() + stdin=DEVNULL keep it sterile and read-only.
        try:
            with TemporaryDirectory() as tmp:
                proc = subprocess.run(
                    argv, cwd=tmp, env=raw_harness_env(Path(tmp)), capture_output=True, text=True,
                    stdin=subprocess.DEVNULL, timeout=timeout_s, check=False,
                )
        except (subprocess.SubprocessError, OSError) as exc:
            return ReviewReport(approved=False, summary=f"review error: {exc}"[:200])
        return parse_review_reply(proc.stdout or "")

    return review_fn


def build_reviewer(
    codegen: CodeGenAdapter,
    requirements: Sequence[Any],
    *,
    files_provider: FilesProvider | None = None,
    comments_sink: dict[str, Any] | None = None,
) -> CortexReviewerJudge:
    """Wire a `CortexReviewerJudge` to a real-CLI review pass over the SAME provider as `codegen`."""

    return CortexReviewerJudge(
        run_cli_review(codegen), requirements,
        files_provider=files_provider, comments_sink=comments_sink,
    )
