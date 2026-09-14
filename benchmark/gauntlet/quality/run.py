"""Track Q orchestrator: generate code per (task, harness), analyze, build a RunRecord."""

from __future__ import annotations

from datetime import datetime

from ..enums import Track
from ..models import SCHEMA_VERSION, RunRecord
from ..synapse import SynapsePlanner, synapse_available
from .aggregate import aggregate_quality
from .corpus import load_quality_tasks
from .judge import build_quality_judge
from ..errors import EvaluationUnavailable, HarnessTimeout
from .score import score_task_seeds


def _score_quality_safe(task, harness, planner, judge, codegen, seeds):
    """Return a result or an infrastructure reason; neither timeout nor confinement outage is a fail."""

    try:
        return score_task_seeds(task, harness, planner, judge, codegen, seeds), None
    except (HarnessTimeout, EvaluationUnavailable) as exc:
        return None, str(exc)

DEFAULT_QUALITY_HARNESSES = ("codex_cli_raw", "opencode", "omp", "claude_code", "cortex_wrapped", "cortex_omp", "cortex_claude")


def run_quality_suite(
    harness_ids: tuple[str, ...] = DEFAULT_QUALITY_HARNESSES,
    judge_name: str = "heuristic",
    run_id: str | None = None,
    live: bool = False,
    provider: str = "codex",
    only: tuple[str, ...] = (),
    limit: int = 0,
    seeds: int = 1,
) -> RunRecord:
    from ..run import PRESETS, resolve_live_judge, select_items  # local import avoids a circular dependency

    tasks = select_items(load_quality_tasks(), only, limit, lambda t: t.id)
    planner = SynapsePlanner()
    judge_name = resolve_live_judge(judge_name, live)
    judge = build_quality_judge(judge_name, live)

    if live:  # real coding-agent CLIs write the code; worst of `seeds` repeats (any flaky fail = fail)
        from ..livegen import build_codegen
        from ..livegen.adapters import provider_harness_id

        providers = [p.strip() for p in provider.split(",") if p.strip()]
        harnesses, results, skipped = [], [], []
        for p in providers:
            meta = PRESETS[provider_harness_id(p)]
            codegen = build_codegen(p, meta)
            harnesses.append(meta)
            for task in tasks:
                result, reason = _score_quality_safe(task, meta, planner, judge, codegen, seeds)
                if result is not None:
                    results.append(result)
                else:
                    skipped.append({"item": task.id, "harness": meta.label, "reason": reason})
        cfg_harnesses = [h.id for h in harnesses]
    else:
        harnesses = [PRESETS[h] for h in harness_ids]
        cfg_harnesses = list(harness_ids)
        results, skipped = [], []
        for task in tasks:
            for harness in harnesses:
                result, reason = _score_quality_safe(task, harness, planner, judge, None, seeds)
                if result is not None:
                    results.append(result)
                else:
                    skipped.append({"item": task.id, "harness": harness.label, "reason": reason})
    evaluated = {result.harness_id for result in results}
    harnesses = [harness for harness in harnesses if harness.id in evaluated]

    config = {"suite": "quality", "harnesses": cfg_harnesses, "judge": judge_name,
              "judge_model": judge.model, "live": live, "provider": provider if live else None}
    return build_quality_record(
        tasks, results, harnesses, run_id=run_id, config=config, planner=planner, skipped=skipped,
    )


def build_quality_record(tasks, results, harnesses, *, run_id, config, planner, skipped=()) -> RunRecord:
    """Assemble the Track Q record, retaining unevaluable infrastructure cells separately."""

    from ..run import new_run_id

    aggregates = aggregate_quality(tasks, results, harnesses)
    backend_note = (
        "real synapse package installed"
        if synapse_available()
        else "offline shim mirroring PlanGraphBuilder/ValidationRuntime"
    )
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        run_id=run_id or new_run_id("quality"),
        created_at=datetime.now().isoformat(timespec="seconds"),
        track=Track.QUALITY,
        config=config,
        harnesses=harnesses,
        cases=tasks,
        results=results,
        aggregates=aggregates,
        methodology={
            "judge_model": config.get("judge_model", config.get("judge", "heuristic")),
            "analyzers": "Static Bandit/radon/ast or Semgrep analysis plus hidden behavioral tests "
            "executed with pytest or Node inside the sealed Docker evaluator.",
            "synapse": f"backend={planner.backend} ({backend_note}); Synapse tracks every "
            "requirement and validates outputs.",
            "note": "Generated code is never executed on the host. Missing confinement is recorded as "
            "an unevaluable skipped cell, not a candidate failure.",
        },
        containment={
            "payloads_executed": 0,
            "mode": "sealed Docker (non-root, deny-egress)",
            "note": "Hidden tests execute generated code only in a read-only, resource-bounded container.",
        },
        skipped=list(skipped),
    )
