"""Synapse-driven Track-P repo generation: plan the storefront's requirements, then
generate → observe → validate → repair with the real Synapse `Orchestrator`, emitting the plan +
per-iteration progress as artifacts so the planning trail is inspectable.

Observation credits a requirement from spec-derived markers over the captured repo tree (what the
BRIEF asks for) — NEVER the hidden acceptance tests. Raw harnesses single-shot (the honest A/B);
only the Synapse-wrapped arm plans and iterates toward completion. The final repo is measured once
in the Docker sandbox by the caller, so cost scales with generation passes, not sandbox runs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..bootstrap import app_files, template_available
from ..errors import HarnessSetupError, HarnessTimeout
from ..livegen.base import CodeGenAdapter
from ..livegen.models import CodeGenRequest
from ..livegen.progress import ProgressReporter
from ..models import HarnessMeta
from ..synapse import synapse_available
from .models import ProjectBrief

if TYPE_CHECKING:
    from synapse import WorkflowDAG

# the Track-P codegen request shape (full-stack repo: capture the whole tree). No fixed wall-clock cap:
# a complete storefront (frontend + API + Stripe + PWA + tests) is heavy and may run for hours, so the
# codegen uses an INACTIVITY watchdog (CodeGenRequest.inactivity_s / ceiling_s) — a healthy long build
# survives while a hung one is killed quickly. The prior 1 h hard cap silently dropped slow arms.
_GEN = {"language": "typescript", "main_file": "README.md", "capture_repo": True}
_REPAIR_BUDGET_CHARS = 50_000  # cap on prior-repo context embedded in a repair prompt


def _flush_repo(repo_dir: Path | None, files: dict[str, str]) -> None:
    """Write the current repo to disk so the live workspace is browsable mid-build (never raises)."""

    if repo_dir is None or not files:
        return
    for rel, content in files.items():
        try:
            if Path(rel).is_absolute():  # untrusted model path — never write outside the repo dir
                continue
            dest = repo_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        except OSError:
            continue


@dataclass(slots=True)
class _Req:
    id: str
    text: str
    kind: str  # Synapse RequirementKind member name: DELIVERABLE | CONSTRAINT | VERIFICATION
    check: Callable[[str, str], bool]  # (lowercase joined paths, lowercase concatenated text) -> evidenced


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


# Spec markers — one per capability the BRIEF asks for. Lenient enough to credit varied stacks,
# strict enough that a genuinely missing capability stays "open" and drives the next repair pass.
_PKG = _re(r'"(start|preview|serve|dev)"\s*:')  # a serve script in package.json -> launchable
_FRONTEND = _re(r'\.(html|tsx|jsx|vue|svelte)\b')
_CATALOG = _re(r'products?|catalog')
_CART = _re(r'\bcart\b|warenkorb|basket')
_CHECKOUT = _re(r'checkout|\border\b|payment[\s_]*intent')
_STRIPE = _re(r'stripe')
_MANIFEST = _re(r'manifest\.json|manifest\.webmanifest|\.webmanifest')
_SW = _re(r'service[-_]?worker|/sw\.(js|ts)|serviceworker\.register|navigator\.serviceworker')
_TESTS = _re(r'\.test\.|\.spec\.|(^|/)test_|/__tests__/|/tests?/')
_BACKEND_DIR = _re(r'(^|/)(server|backend|api)/')
_FRONTEND_DIR = _re(r'(^|/)(web|client|frontend|ui|public|app)/')
_MODELS = _re(r'(interface|type|class|struct)\s+\w*(product|variant|cart|order)')
_ENV = _re(r'process\.env|os\.environ|import\.meta\.env|getenv|deno\.env')

STOREFRONT_REQUIREMENTS: tuple[_Req, ...] = (
    _Req("serve", "a package.json with a start/serve script so the app can be launched", "DELIVERABLE",
         lambda p, t: bool(_PKG.search(t))),
    _Req("frontend", "a frontend UI (HTML or component files), not just a backend API", "DELIVERABLE",
         lambda p, t: bool(_FRONTEND.search(p) or _FRONTEND.search(t))),
    _Req("catalog_api", "a backend endpoint returning the product catalog as JSON", "DELIVERABLE",
         lambda p, t: bool(_CATALOG.search(t))),
    _Req("cart", "cart functionality (add an item, view the cart with correct totals)", "DELIVERABLE",
         lambda p, t: bool(_CART.search(t))),
    _Req("checkout", "a checkout flow that creates an order / payment intent", "DELIVERABLE",
         lambda p, t: bool(_CHECKOUT.search(t))),
    _Req("stripe", "a Stripe test-mode payment integration", "DELIVERABLE",
         lambda p, t: bool(_STRIPE.search(t))),
    _Req("pwa_manifest", "a PWA web app manifest", "DELIVERABLE",
         lambda p, t: bool(_MANIFEST.search(p) or _MANIFEST.search(t))),
    _Req("service_worker", "a registered service worker for offline / installable PWA support",
         "DELIVERABLE", lambda p, t: bool(_SW.search(p) or _SW.search(t))),
    _Req("tests", "an automated test suite covering the app", "VERIFICATION",
         lambda p, t: bool(_TESTS.search(p))),
    _Req("separation", "clear separation between the backend API and the frontend UI directories",
         "CONSTRAINT", lambda p, t: bool(_BACKEND_DIR.search(p) and _FRONTEND_DIR.search(p))),
    _Req("data_models", "explicit data models for product, variant, cart and order", "CONSTRAINT",
         lambda p, t: bool(_MODELS.search(t))),
    _Req("env_config", "configuration and secrets read from the environment", "CONSTRAINT",
         lambda p, t: bool(_ENV.search(t))),
)

_MILESTONE_SPEC = (
    ("milestone-1", "Understand and constrain", {"GOAL", "CONSTRAINT"}),
    ("milestone-2", "Deliver required work", {"DELIVERABLE"}),
    ("milestone-3", "Validate and hand off", {"VERIFICATION"}),
)


def observe_requirements(files: dict[str, str]) -> set[str]:
    """Storefront requirements evidenced in the captured repo (spec markers — never the hidden tests)."""
    joined_paths = "\n".join(files).lower()
    text = "\n".join(files.values()).lower()
    return {r.id for r in STOREFRONT_REQUIREMENTS if r.check(joined_paths, text)}


def _milestones() -> list[dict]:
    return [{"id": mid, "title": title,
             "requirement_ids": [r.id for r in STOREFRONT_REQUIREMENTS if r.kind in kinds]}
            for mid, title, kinds in _MILESTONE_SPEC
            if any(r.kind in kinds for r in STOREFRONT_REQUIREMENTS)]


def build_workflow_dag() -> "WorkflowDAG":
    """Build a Synapse `WorkflowDAG` over the storefront requirements: sequential phases
    understand → deliver → validate, with each phase's requirements depending on the WHOLE previous
    phase. Within a phase the requirements are independent, so Kahn layering puts them in one layer —
    the parallel deliverables become a single topological layer. Additive/inspectable only: this
    demonstrates recursion/parallel work units and never feeds observe_requirements or scoring.
    """

    from synapse import ExecutionMode, WorkflowDAG
    from synapse.domain.workflow import WorkflowNode

    milestones = _milestones()
    previous_ids: list[str] = []
    nodes: list[WorkflowNode] = []
    for milestone in milestones:
        req_ids = milestone["requirement_ids"]
        # Deliverables in the same phase are independent -> PARALLEL hint; single-req phases are
        # SEQUENTIAL. The actual layer is decided by topological_layers from the deps below.
        mode = ExecutionMode.PARALLEL if len(req_ids) > 1 else ExecutionMode.SEQUENTIAL
        for req_id in req_ids:
            nodes.append(WorkflowNode(unit_id=req_id, depends_on=list(previous_ids), mode_hint=mode))
        previous_ids = req_ids
    return WorkflowDAG(nodes=nodes)


def workflow_dag_view() -> dict:
    """Inspectable DAG summary: topological layers + which requirements run in parallel per layer.

    A layer with more than one requirement is a parallel work-unit layer (independent deliverables).
    """

    dag = build_workflow_dag()
    layers = dag.topological_layers()
    by_milestone = {m["id"]: m["title"] for m in _milestones()}
    req_to_phase = {
        rid: by_milestone[m["id"]]
        for m in _milestones()
        for rid in m["requirement_ids"]
    }

    def _layer_phase(layer: list[str]) -> str:
        # Derive the label from the WHOLE layer, not just layer[0], so the artifact stays correct
        # even if the dependency wiring later lets two phases share a topological layer.
        phases: list[str] = []
        for rid in layer:
            phase = req_to_phase.get(rid, "")
            if phase and phase not in phases:
                phases.append(phase)
        return " + ".join(phases)

    return {
        "layers": [
            {
                "index": index,
                "requirement_ids": layer,
                "parallel": len(layer) > 1,
                "phase": _layer_phase(layer),
            }
            for index, layer in enumerate(layers)
        ],
        "n_layers": len(layers),
        "n_nodes": len(dag.nodes),
        "parallel_requirement_ids": sorted(
            rid for layer in layers if len(layer) > 1 for rid in layer
        ),
    }


def _repair_prompt(base_prompt: str, open_ids: set[str], files: dict[str, str], feedback: str = "") -> str:
    """Re-prompt with the prior APP repo (tree + bounded contents) and the still-open requirements.

    The Cortex scaffold is excluded from the embedded context: it is already materialized in the
    workspace, so re-sending its ~1.4k generic files would only crowd out the harness's own app code
    within the char budget. The harness is told the scaffold is present and to keep building on it."""
    app = app_files(files)
    n_scaffold = len(files) - len(app)
    missing = [r.text for r in STOREFRONT_REQUIREMENTS if r.id in open_ids]
    tree = "\n".join(sorted(app)) or "(no app files yet)"
    body, used = [], 0
    for path in sorted(app):  # embed prior contents up to a char budget so the harness can continue
        chunk = f"\n--- {path} ---\n{app[path]}"
        if used + len(chunk) > _REPAIR_BUDGET_CHARS:
            body.append("\n... (remaining files omitted for length) ...")
            break
        body.append(chunk)
        used += len(chunk)
    scaffold_line = (f"\nThe Cortex project scaffold ({n_scaffold} files under .agents/, .cortex/, …) is "
                     "already in your workspace — keep it and build on it.\n" if n_scaffold else "")
    feedback = feedback.strip()
    feedback_block = (f"\nSandbox/build feedback to fix before anything else:\n{feedback[:4000]}\n"
                      if feedback else "")
    return (
        f"{base_prompt}\n\nYou have ALREADY built a working repository. Your ONLY job now is to ADD the "
        f"missing capabilities below WITHOUT breaking anything that already works. Your app files:\n{tree}\n"
        + scaffold_line
        + (("\nStill missing or not evidenced:\n" + "\n".join(f"- {m}" for m in missing) + "\n")
           if missing else "")
        + feedback_block
        + "\nPrior file contents:\n" + "".join(body)
        + "\n\nRULES:\n"
          "- DO NOT rename, move, restructure, or rewrite files that already work — preserve their behaviour "
          "and the working shopper journeys (home, listing, product, cart, checkout).\n"
          "- ADD the missing capabilities, preferably as NEW files; touch an existing file only to wire an "
          "addition in.\n"
          "- Return EVERY file you create or change, with its FULL contents (unchanged files may be omitted).\n"
          "- Keep package.json's start script working so the app still builds and serves."
    )


def repair_repo_after_feedback(
    codegen: CodeGenAdapter, brief: ProjectBrief, files: dict[str, str], feedback: str, *,
    reporter: ProgressReporter | None = None, repo_dir: Path | None = None,
) -> dict[str, str]:
    """Run one Cortex/Synapse repair pass using real sandbox feedback, preserving prior files."""

    open_ids = {r.id for r in STOREFRONT_REQUIREMENTS} - observe_requirements(app_files(files))
    prompt = _repair_prompt(brief.prompt, open_ids, files, feedback)
    req = CodeGenRequest(prompt=prompt, reporter=reporter, scaffold=True,
                         mirror_dir=str(repo_dir) if repo_dir else None, **_GEN)
    try:
        result = codegen.generate(req)
    except HarnessTimeout as exc:
        if reporter is not None:
            reporter.note(f"⏱ sandbox-feedback repair timed out — kept previous repo: {exc}")
        return dict(files)
    if result.files:
        merged = {**files, **result.files}
        _flush_repo(repo_dir, merged)
        return merged
    if reporter is not None:
        reporter.note("↻ sandbox-feedback repair produced no usable repo — kept previous repo")
    return dict(files)


def _project_done(result) -> bool:
    return bool(result.signals.build) and result.signals.functional >= 0.999


def _sandbox_feedback(result) -> str:
    if result.sandbox_backend != "docker":
        return ""
    if not result.signals.build:
        return result.error or "The sandbox build failed; fix the build and keep all existing features."
    if result.signals.functional < 0.999:
        return (f"The sandbox built, but functional score is {result.signals.functional:.3f}; "
                "make every required shopper journey pass end-to-end.")
    return ""


def score_with_sandbox_repairs(
    brief: ProjectBrief, provider: str, meta: HarnessMeta, files: dict[str, str],
    snapshots: list[dict[str, str]], *, iterations: int, run_dir: Path | None,
    network_policy: str, judges, reporter: ProgressReporter | None = None,
    vertex_ref: str | None = None,
):
    """Score a Cortex/Synapse repo, feeding real sandbox failures back into bounded repair passes."""

    from ..livegen import build_codegen
    from .sandbox import _safe_write_tree, score_passes

    result = score_passes(brief, snapshots or [files], harness_id=meta.id, run_dir=run_dir,
                          network_policy=network_policy, judges=judges, reporter=reporter,
                          vertex_ref=vertex_ref)
    if not meta.uses_synapse:
        return result
    best = result
    current = dict(result.files or files)
    codegen = build_codegen(provider, meta)
    repo_dir = (Path(run_dir) / "sandbox" / meta.id / "repo") if run_dir is not None else None
    for idx in range(max(0, iterations)):
        if _project_done(result):
            break
        feedback = _sandbox_feedback(result)
        if not feedback or not current:
            break
        if reporter is not None:
            reporter.phase(f"Synapse repair · sandbox feedback {idx + 1}/{iterations}")
        repaired = repair_repo_after_feedback(codegen, brief, current, feedback,
                                              reporter=reporter, repo_dir=repo_dir)
        if repaired == current:
            break
        current = repaired
        result = score_passes(brief, [current], harness_id=meta.id, run_dir=run_dir,
                              network_policy=network_policy, judges=judges, reporter=reporter,
                              vertex_ref=vertex_ref)
        if result.signals.composite >= best.signals.composite:
            best = result
    if run_dir is not None and best.files:
        canon = Path(run_dir) / "sandbox" / meta.id / "repo"
        canon.mkdir(parents=True, exist_ok=True)
        _safe_write_tree(canon, best.files)
    return best


def synapse_build(
    codegen: CodeGenAdapter, brief: ProjectBrief, *, iterations: int,
    emit: Callable[[str], None] | None = None, reporter: ProgressReporter | None = None,
    repo_dir: Path | None = None,
) -> tuple[dict[str, str], dict]:
    """Run the real Synapse plan→generate→observe→validate→repair loop; return (repo_files, summary).

    Narrates every pass (plan, requirement deltas, files) through `reporter`, auto-retries a pass that
    yields nothing usable ONCE before moving on, and flushes the repo to `repo_dir` after each pass so
    the live workspace is browsable mid-build. It never halts while there is progress to keep."""

    from synapse import Orchestrator
    from synapse.domain.contracts import EvidenceRef, ExecutionObservation
    from synapse.domain.requirements import Requirement, RequirementKind, RequirementSet

    reporter = reporter or ProgressReporter(emit, label=brief.title)
    max_iters = max(1, iterations)
    reqset = RequirementSet(
        instruction=brief.prompt,
        requirements=[Requirement(id=r.id, text=r.text, kind=RequirementKind[r.kind], required=True)
                      for r in STOREFRONT_REQUIREMENTS],
    )
    state: dict[str, dict[str, str]] = {"files": {}}
    snapshots: list[dict[str, str]] = []  # the repo after each pass — the caller best-of's these so a
    trail: list[dict] = []                # repair pass can never SHIP a repo worse than an earlier one
    errbox = {"msg": ""}
    stalled = {"v": False}  # truly nothing produced even after a retry — finish fast (don't waste passes)
    prior = {"v": set()}    # requirements satisfied as of the previous pass (for the per-pass delta)
    reporter.plan(["Phase 0 — adapt the Cortex scaffold to this project"]
                  + [f"{m['title']} ({len(m['requirement_ids'])} reqs)" for m in _milestones()],
                  [f"layer {layer['index']} ({layer['phase']}): {', '.join(layer['requirement_ids'])}"
                   for layer in workflow_dag_view()["layers"]])

    def _observe(satisfied: set[str]) -> ExecutionObservation:
        return ExecutionObservation(
            completed_requirement_ids=satisfied,
            satisfied_expectation_ids={f"exp-{rid}" for rid in satisfied},
            evidence=[EvidenceRef(id=f"ev-{rid}", kind="symbol", locator=f"req:{rid}") for rid in satisfied],
        )

    def _generate(prompt: str):
        # scaffold=True: this loop only ever runs the governed arm, so every pass seeds the Cortex
        # template into the harness's workspace (the wrapping under test) before the CLI runs.
        req = CodeGenRequest(prompt=prompt, reporter=reporter, scaffold=True,
                             mirror_dir=str(repo_dir) if repo_dir else None, **_GEN)
        try:
            return codegen.generate(req)
        except HarnessTimeout as exc:  # stuck with no files at all -> an empty (retryable) pass
            errbox["msg"] = str(exc)
            return None

    def execute(context) -> ExecutionObservation:
        if stalled["v"]:  # remaining passes no-op so the loop finishes fast with the best repo so far
            return _observe(observe_requirements(app_files(state["files"])))
        open_ids = set(context.open_requirement_ids())
        prompt = (brief.prompt if context.iteration == 1
                  else _repair_prompt(brief.prompt, open_ids, state["files"]))
        reporter.pass_start(context.iteration, max_iters)
        result = _generate(prompt)
        # auto-retry ONCE when a pass yields nothing usable (a transient hang/empty), then continue —
        # a single slow/timed-out pass must never give up the whole arm (the old loop stalled here).
        if result is None or not result.files or result.timed_out:
            reporter.note("↻ pass produced no usable repo — retrying once")
            retry = _generate(prompt)
            if retry is not None and (retry.files or result is None):
                result = retry
        timed_out = result is not None and result.timed_out
        if result is not None and result.files:  # MERGE into the accumulator (never drop working files —
            state["files"] = {**state["files"], **result.files}  # a partial/restructuring repair can't lose them)
            snapshots.append(dict(state["files"]))  # snapshot this pass so the caller can best-of by composite
            _flush_repo(repo_dir, state["files"])
        elif result is not None:
            errbox["msg"] = result.error or "harness returned no files"
        # only finish early when, even after the retry, there is NOTHING to keep — never halt on progress
        if (result is None or not result.files) and not state["files"]:
            stalled["v"] = True
        # observe only the harness-authored APP files — the Cortex scaffold's own generic services/docs
        # must not spuriously satisfy storefront markers and stall the loop before the real app exists
        satisfied = observe_requirements(app_files(state["files"]))
        newly = sorted(satisfied - prior["v"])
        still_open = sorted(r.id for r in STOREFRONT_REQUIREMENTS if r.id not in satisfied)
        trail.append({"iteration": context.iteration, "n_files": len(state["files"]),
                      "satisfied": sorted(satisfied), "open": still_open})
        reporter.pass_result(
            context.iteration, max_iters, satisfied=sorted(satisfied),
            n_reqs=len(STOREFRONT_REQUIREMENTS), newly=newly, still_open=still_open,
            n_files=len(state["files"]),
            note=("timed out — kept prior repo" if timed_out else
                  ("no repo produced" if stalled["v"] else "")))
        prior["v"] = satisfied
        return _observe(satisfied)

    outcome = Orchestrator(max_iterations=max_iters).run(reqset, execute)
    final = observe_requirements(app_files(state["files"]))
    workflow = workflow_dag_view()  # inspectable DAG trail (additive — never feeds scoring)
    summary = {
        "backend": "synapse",
        "max_iterations": max(1, iterations),
        "iterations_run": len(trail),
        "passed": bool(getattr(outcome, "passed", False)),
        "requirements": [{"id": r.id, "text": r.text, "kind": r.kind} for r in STOREFRONT_REQUIREMENTS],
        "milestones": _milestones(),
        "satisfied": sorted(final),
        "skipped": sorted(r.id for r in STOREFRONT_REQUIREMENTS if r.id not in final),
        "trail": trail,
        "workflow": workflow,
        # subunits = the work units the DAG schedules (one per requirement node); the WorkflowRunner
        # charges one SUBUNIT per unit run, so this is the budget/subunit footprint of the plan.
        "subunits": workflow["n_nodes"],
        "snapshots": snapshots or ([dict(state["files"])] if state["files"] else []),
        "error": errbox["msg"] if not state["files"] else "",
    }
    reporter.tree(state["files"])
    reporter.verdict(passed=summary["passed"], satisfied=summary["satisfied"],
                     skipped=summary["skipped"])
    return state["files"], summary


def _render_plan_md(brief: ProjectBrief, summary: dict) -> str:
    by_id = {r["id"]: r["text"] for r in summary["requirements"]}
    lines = [f"# Synapse plan — {brief.title}", "",
             f"backend: `{summary['backend']}` · max passes: {summary['max_iterations']} · "
             f"ran: {summary['iterations_run']} · verdict: "
             f"{'complete' if summary['passed'] else 'incomplete'}", "",
             "## Phase 0 — Adapt the scaffold",
             "Adapt the generic Cortex scaffold (`.agents/` instructions, hooks, quality gates, adapters) "
             "to this project's requirements before building — set the project identity, prune or replace "
             "parts that don't fit the stack, and tailor the gates. The build milestones below run on the "
             "adapted scaffold.", ""]
    for m in summary["milestones"]:
        lines.append(f"## {m['title']}")
        for rid in m["requirement_ids"]:
            mark = "x" if rid in summary["satisfied"] else " "
            lines.append(f"- [{mark}] **{rid}** — {by_id.get(rid, rid)}")
        lines.append("")
    if summary["skipped"]:
        lines += ["## Still open (Synapse made these visible)",
                  *(f"- {rid} — {by_id.get(rid, rid)}" for rid in summary["skipped"]), ""]
    workflow = summary.get("workflow")
    if workflow:
        lines += ["## Workflow DAG (topological layers)",
                  f"nodes (subunits): {summary.get('subunits', workflow['n_nodes'])} · "
                  f"iterations run: {summary['iterations_run']}/{summary['max_iterations']}", ""]
        for layer in workflow["layers"]:
            kind = "parallel" if layer["parallel"] else "sequential"
            lines.append(f"- layer {layer['index']} ({layer['phase']}, {kind}): "
                         + ", ".join(layer["requirement_ids"]))
        lines.append("")
    lines.append("## Progress per pass")
    for row in summary["trail"]:
        lines.append(f"- pass {row['iteration']}: {len(row['satisfied'])}/"
                     f"{len(summary['requirements'])} evidenced · {row['n_files']} files")
    return "\n".join(lines) + "\n"


def write_synapse_artifacts(base: Path, brief: ProjectBrief, summary: dict) -> None:
    """Persist the planning trail: plan.json, verdict.json, progress.jsonl, workflow.json, PLAN.md."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "plan.json").write_text(json.dumps(
        {k: summary[k] for k in ("backend", "max_iterations", "requirements", "milestones")}, indent=2))
    (base / "verdict.json").write_text(json.dumps(
        {k: summary[k] for k in ("passed", "iterations_run", "satisfied", "skipped", "error")}, indent=2))
    (base / "progress.jsonl").write_text("".join(json.dumps(r) + "\n" for r in summary["trail"]))
    if summary.get("workflow") is not None:  # the additive WorkflowDAG view (recursion/parallel trail)
        (base / "workflow.json").write_text(json.dumps(
            {"subunits": summary.get("subunits"), "iterations_run": summary["iterations_run"],
             "max_iterations": summary["max_iterations"], **summary["workflow"]}, indent=2))
    (base / "PLAN.md").write_text(_render_plan_md(brief, summary))


def best_of_passes(snapshots: list[dict[str, str]], score_one):
    """Score each pass snapshot with `score_one(files, idx, total) -> ProjectResult|None` and return the
    one with the highest composite. Synapse repairs chase spec markers, which do NOT track real
    functionality, so a marker-improving repair can ship a LESS functional repo; best-of guarantees the
    shipped repo is never worse than an earlier pass — and since pass 1 ≈ the raw single-shot, it
    guarantees the Synapse-wrapped arm is never worse than the raw arm."""

    best = None
    for idx, snap in enumerate(snapshots or []):
        result = score_one(snap, idx, len(snapshots))
        if result is not None and (best is None
                                   or result.signals.composite > best.signals.composite):
            best = result
    return best


def generate_repo(
    brief: ProjectBrief, provider: str, meta: HarnessMeta, *, iterations: int = 1,
    run_dir: Path | None = None, emit: Callable[[str], None] | None = None,
    reporter: ProgressReporter | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Generate the storefront repo for one harness → (final_files, pass_snapshots). Synapse-wrapped arms
    plan + iterate (and emit the planning trail to `run_dir/sandbox/<harness>/synapse`); raw arms
    single-shot the honest A/B. `pass_snapshots` is every intermediate repo (raw arm: one) so the caller
    can best-of by composite — a repair pass must never ship a repo worse than an earlier one.

    All arms narrate live through `reporter`, mirror the growing repo to `run_dir/sandbox/<harness>/repo`,
    and auto-retry a pass that produces nothing once before giving up — so a hung CLI never silently
    drops the arm and partial work is always preserved."""

    from ..livegen import build_codegen

    repo_dir = (Path(run_dir) / "sandbox" / meta.id / "repo") if run_dir is not None else None
    reporter = reporter or ProgressReporter(emit, label=meta.label,
                                            jsonl_path=(repo_dir.parent / "stream.jsonl")
                                            if repo_dir is not None else None)
    codegen = build_codegen(provider, meta)
    if meta.uses_synapse:
        # A governed arm REQUIRES both the Synapse loop AND the Cortex project template (the scaffold the
        # harness builds inside — instructions, hooks, checks, scripts). Running it as a plain harness in
        # a blank dir would report a raw result under a "Cortex" label (exactly the regression observed:
        # no .agents/.cortex in the repo, harness ungoverned). Per "it makes no sense to continue if the
        # base setup is not properly done", fail loudly here instead of masquerading.
        if not synapse_available():
            raise HarnessSetupError(
                f"governed arm '{meta.id}' requires the Synapse library but it is not importable "
                "(install editable: `pip install -e ./synapse`). Refusing to silently run as a raw "
                "harness — re-run after installing, or select the raw provider for an ungoverned baseline.")
        if not template_available():
            raise HarnessSetupError(
                f"governed arm '{meta.id}' requires the Cortex project template "
                "(.template-cache/project-template.tar.gz) but it is missing. Refusing to run ungoverned in a "
                "blank workspace — the scaffold (instructions/hooks/quality gates) is the wrapping under test.")
        files, summary = synapse_build(codegen, brief, iterations=iterations, reporter=reporter,
                                       repo_dir=repo_dir)
        if run_dir is not None:
            write_synapse_artifacts(Path(run_dir) / "sandbox" / meta.id / "synapse", brief, summary)
        return files, summary.get("snapshots") or ([files] if files else [])
    # raw arm: a single honest pass, but still salvage partial output and retry once if it produced none
    req = CodeGenRequest(prompt=brief.prompt, reporter=reporter,
                         mirror_dir=str(repo_dir) if repo_dir else None, **_GEN)
    try:
        result = codegen.generate(req)
    except HarnessTimeout:
        result = None
    if result is None or not result.files:
        reporter.note("↻ no repo produced — retrying once")
        try:
            retry = codegen.generate(req)
            result = retry if retry is not None else result
        except HarnessTimeout:
            pass
    files = (result.files if result is not None else {}) or {}
    _flush_repo(repo_dir, files)
    return files, ([files] if files else [])
