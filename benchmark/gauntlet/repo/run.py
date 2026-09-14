"""Track R orchestrator: resolve each repo issue per harness (mock or live), aggregate resolution rate."""

from __future__ import annotations

from datetime import datetime

from ..enums import Track
from ..errors import EvaluationUnavailable, HarnessTimeout
from ..models import SCHEMA_VERSION, RunRecord
from ..synapse import synapse_available
from .corpus import load_repo_tasks
from .models import RepoResult, RepoTask
from .score import score_repo_task_seeds

DEFAULT_REPO_HARNESSES = ("codex_cli_raw", "opencode", "omp", "claude_code", "cortex_wrapped", "cortex_omp", "cortex_claude")


def _score_repo_safe(task, harness, codegen, seeds, judge=None):
    """Return a result or an unevaluable infrastructure reason."""

    try:
        return score_repo_task_seeds(task, harness, codegen, seeds, judge), None
    except (HarnessTimeout, EvaluationUnavailable) as exc:
        return None, str(exc)


def _repo_checks(rows: list[RepoResult]) -> dict:
    from ..checks import checks_block

    func = (sum(r.tests_passed for r in rows), sum(r.tests_total for r in rows))  # FAIL_TO_PASS
    held = (sum(r.held_out_passed for r in rows), sum(r.held_out_total for r in rows))  # anti-overfit
    reg = (sum(r.regression_passed for r in rows), sum(r.regression_total for r in rows))  # PASS_TO_PASS
    qual = (sum(2.0 * r.code_quality for r in rows), 2.0 * len(rows))            # ruff + mypy (2 checks)
    block: dict[str, tuple[float, float]] = {"functionality": func}
    if held[1]:
        block["robustness"] = held
    if reg[1]:
        block["regression"] = reg
    block["quality"] = qual
    return checks_block(block)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def aggregate_repo(tasks: list[RepoTask], results: list[RepoResult], harnesses: list) -> dict:
    """Per-harness graded metrics: lenient + strict resolution (Wilson CI), the composite, each graded
    axis, a per-difficulty breakdown, and a raw-vs-cortex delta on the COMPOSITE (the discriminator)."""

    from ..scoring.stats import wilson_interval
    diff_of = {t.id: t.difficulty for t in tasks}
    by_h = {h.id: [r for r in results if r.harness_id == h.id] for h in harnesses}
    uses_synapse = {h.id: h.uses_synapse for h in harnesses}
    per_harness: dict[str, dict] = {}
    for hid, rows in by_h.items():
        n = len(rows)
        resolved = sum(r.resolved for r in rows)
        strict = sum(r.strict_resolved for r in rows)
        lo, hi = wilson_interval(resolved, n)
        slo, shi = wilson_interval(strict, n)
        by_difficulty = {}
        for tier in ("easy", "hard"):
            tr = [r for r in rows if diff_of.get(r.task_id) == tier]
            if tr:
                by_difficulty[tier] = {
                    "n": len(tr), "strict_rate": round(sum(r.strict_resolved for r in tr) / len(tr), 4),
                    "composite": _mean([r.composite for r in tr])}
        per_harness[hid] = {
            "resolved": resolved, "n": n,
            "resolution_rate": round(resolved / n, 4) if n else None,
            "ci": [round(v, 4) if v is not None else None for v in (lo, hi)],
            "strict_resolved": strict, "strict_rate": round(strict / n, 4) if n else None,
            "strict_ci": [round(v, 4) if v is not None else None for v in (slo, shi)],
            "composite": _mean([r.composite for r in rows]) if n else None,
            # graded axes are meaningful only where a fix actually landed: a do-nothing patch trivially
            # scores minimality=1/regression=1, so averaging it in would reward failure — the composite
            # already zeroes unresolved rows, and these per-axis means must match that basis
            "robustness": _mean([r.robustness for r in rows if r.resolved]),
            "regression": _mean([r.regression for r in rows if r.resolved]),
            "locality": _mean([r.patch_locality for r in rows if r.resolved]),
            "minimality": _mean([r.patch_minimality for r in rows if r.resolved]),
            "semantic_patch_quality": _mean([
                r.semantic_patch_quality for r in rows if r.semantic_patch_quality is not None
            ]),
            "code_health": _mean([r.code_quality for r in rows]),
            "cheats": sum(r.cheated for r in rows),
            "errors": sum(bool(r.gen_error) for r in rows),
            "by_difficulty": by_difficulty,
            "checks": _repo_checks(rows),  # test-counted: FAIL_TO_PASS + held-out + regression + lint/type
            "uses_synapse": uses_synapse[hid],
        }
    raw = next((h.id for h in harnesses if h.role == "raw"), None)
    cortex = next((h.id for h in harnesses if h.role == "cortex_wrapped"), None)
    delta: dict = {}
    if raw in per_harness and cortex in per_harness and per_harness[raw]["n"] and per_harness[cortex]["n"]:
        a, b = per_harness[raw]["composite"], per_harness[cortex]["composite"]
        ra, rb = per_harness[raw]["resolution_rate"], per_harness[cortex]["resolution_rate"]
        sa, sb = per_harness[raw]["strict_rate"], per_harness[cortex]["strict_rate"]
        delta = {"raw": raw, "cortex_wrapped": cortex, "synapse": cortex,
                 "composite": {"raw": a, "cortex_wrapped": b, "delta": round(b - a, 4)},
                 "resolution_rate": {"raw": ra, "cortex_wrapped": rb, "delta": round(rb - ra, 4)},
                 "strict_rate": {"raw": sa, "cortex_wrapped": sb, "delta": round(sb - sa, 4)}}
    # `synapse_delta` is the key the site's _track_delta reads for the raw-vs-cortex headline
    return {"per_harness": per_harness, "synapse_delta": delta}


def run_repo_suite(
    harness_ids: tuple[str, ...] = DEFAULT_REPO_HARNESSES,
    run_id: str | None = None, live: bool = False, provider: str = "codex",
    only: tuple[str, ...] = (), limit: int = 0, seeds: int = 1, judge_name: str = "heuristic",
) -> RunRecord:
    from ..run import PRESETS, resolve_live_judge, select_items
    from .judge import build_repo_judge

    tasks = select_items(load_repo_tasks(), only, limit, lambda t: t.id)
    judge_name = resolve_live_judge(judge_name, live)
    judge = build_repo_judge(judge_name, live)
    if live:  # one or more real harnesses read each issue and edit the repo (worst of `seeds` repeats)
        from ..livegen import build_codegen
        from ..livegen.adapters import provider_harness_id

        harnesses, results, skipped = [], [], []
        for prov in (p.strip() for p in provider.split(",") if p.strip()):
            meta = PRESETS[provider_harness_id(prov)]
            harnesses.append(meta)
            codegen = build_codegen(prov, meta)
            for task in tasks:
                result, reason = _score_repo_safe(task, meta, codegen, seeds, judge)
                if result is not None:
                    results.append(result)
                else:
                    skipped.append({"item": task.id, "harness": meta.label, "reason": reason})
    else:
        harnesses = [PRESETS[h] for h in harness_ids]
        results, skipped = [], []
        for task in tasks:
            for harness in harnesses:
                result, reason = _score_repo_safe(task, harness, None, seeds, judge)
                if result is not None:
                    results.append(result)
                else:
                    skipped.append({"item": task.id, "harness": harness.label, "reason": reason})
    evaluated = {result.harness_id for result in results}
    harnesses = [harness for harness in harnesses if harness.id in evaluated]
    return build_repo_record(
        tasks, results, harnesses, run_id=run_id, live=live, provider=provider,
        judge_name=judge_name, judge_model=getattr(judge, "model", "heuristic"), skipped=skipped,
    )


def build_repo_record(
    tasks, results, harnesses, *, run_id, live, provider,
    judge_name: str = "heuristic", judge_model: str = "heuristic", skipped=(),
) -> RunRecord:
    """Assemble Track R while retaining unevaluable cells outside the aggregates."""

    from ..run import new_run_id

    basis = ("measured (real harness patch + hidden-test execution)" if live
             else "mock (modelled resolution)")
    backend_note = "real synapse package installed" if synapse_available() else "offline shim"
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        run_id=run_id or new_run_id("repo"),
        created_at=datetime.now().isoformat(timespec="seconds"),
        track=Track.REPO,
        config={"suite": "repo", "harnesses": [h.id for h in harnesses], "live": live,
                "basis": basis, "provider": provider if live else None,
                "judge": judge_name, "judge_model": judge_model},
        harnesses=harnesses,
        cases=[{"id": t.id, "title": t.title, "problem_statement": t.problem_statement} for t in tasks],
        results=results,
        aggregates=aggregate_repo(tasks, results, harnesses),
        methodology={
            "scoring": "Graded, SWE-bench-Pro-inspired: resolution = the shown hidden test (FAIL_TO_PASS) "
            "passes after the arm's patch. Strict resolution additionally requires HELD-OUT tests the arm "
            "never saw (anti-overfit) and PASS_TO_PASS regression tests to pass, with no test-file edits "
            "(stripped + flagged as cheating). The live composite also folds in a semantic patch-quality "
            "judge when configured. The composite [0,1] weights robustness (held-out) 0.40, "
            "regression 0.25, patch minimality 0.15, locality-vs-gold (F1) 0.10, and code health 0.10 — so "
            "two arms that both 'resolve' an easy bug still separate on robustness and patch quality.",
            "synapse": f"backend={backend_note}.",
            "note": f"basis={basis}. Hidden, held-out, and regression tests execute only in the sealed "
            "Docker evaluator; missing confinement is an unevaluable skip. Held-out tests are never "
            "shown to the arm.",
        },
        containment={"payloads_executed": 0, "mode": "sealed Docker (non-root, deny-egress)",
                     "note": "Generated patches execute only in a read-only, resource-bounded container."},
        skipped=list(skipped),
    )
