"""Track G orchestrator: build each app brief per harness over seeds, score, build a RunRecord."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..enums import Track
from ..errors import EvaluationUnavailable
from ..models import SCHEMA_VERSION, RunRecord
from ..synapse import SynapsePlanner
from .aggregate import aggregate_generative
from .corpus import load_briefs
from .generate import run_brief
from .judge import build_generative_judge
from .screenshot import render

DEFAULT_GEN_HARNESSES = ("codex_cli_raw", "opencode", "omp", "claude_code", "cortex_wrapped", "cortex_omp", "cortex_claude")


def run_generative_suite(
    harness_ids: tuple[str, ...] = DEFAULT_GEN_HARNESSES,
    seeds: int = 1,
    judge_name: str = "heuristic",
    run_id: str | None = None,
    assets_dir: Path | None = None,
    live: bool = False,
    provider: str = "codex",
    only: tuple[str, ...] = (),
    limit: int = 0,
) -> RunRecord:
    from ..run import PRESETS, resolve_live_judge, select_items  # local import avoids a circular dependency

    if live and seeds != 1:
        raise ValueError("Live generative execution supports exactly one seed per run")
    planner = SynapsePlanner()
    judge_name = resolve_live_judge(judge_name, live)
    judge = build_generative_judge(judge_name, live)

    if live:  # one or more real harnesses write the app; the e2e runner builds, serves, and measures it
        from ..livegen import build_codegen
        from ..livegen.adapters import provider_harness_id
        from .live import live_briefs, run_live_brief, to_appbrief

        providers = [p.strip() for p in provider.split(",") if p.strip()]
        specs = select_items(live_briefs(), only, limit, lambda b: b["id"])
        briefs = [to_appbrief(b) for b in specs]
        harnesses, results, skipped = [], [], []
        for p in providers:
            meta = PRESETS[provider_harness_id(p)]
            codegen = build_codegen(p, meta)
            harnesses.append(meta)
            for brief in specs:
                try:
                    results.append(run_live_brief(brief, meta, codegen, planner, judge, assets_dir))
                except EvaluationUnavailable as exc:
                    skipped.append({"item": brief["id"], "harness": meta.label, "reason": str(exc)})
    else:
        skipped = []
        briefs = select_items(load_briefs(), only, limit, lambda b: b.id)
        harnesses = [PRESETS[h] for h in harness_ids]
        results = [run_brief(b, h, planner, judge, seeds) for b in briefs for h in harnesses]
        if assets_dir is not None:
            assets_dir.mkdir(parents=True, exist_ok=True)
            by_brief = {b.id: b for b in briefs}
            for r in results:
                r.screenshot = render(by_brief[r.brief_id], r, assets_dir)

    config = {"suite": "generative", "harnesses": [h.id for h in harnesses], "judge": judge_name,
              "judge_model": judge.model, "seeds": 1 if live else seeds,
              "live": live, "provider": provider if live else None}
    return build_generative_record(
        briefs, results, harnesses, run_id=run_id, config=config, planner=planner, seeds=seeds,
        skipped=skipped,
    )


def build_generative_record(
    briefs, results, harnesses, *, run_id, config, planner, seeds, skipped=()
) -> RunRecord:
    """Assemble the Track G RunRecord, preserving unevaluable infrastructure cells separately."""

    from ..run import new_run_id

    aggregates = aggregate_generative(briefs, results, harnesses)
    backend_note = "deterministic local milestone planner; package installation does not change this path"
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        run_id=run_id or new_run_id("generative"),
        created_at=datetime.now().isoformat(timespec="seconds"),
        track=Track.GENERATIVE,
        config=config,
        harnesses=harnesses,
        cases=briefs,
        results=results,
        aggregates=aggregates,
        methodology={
            "judge_model": f"{config.get('judge_model', config.get('judge', 'heuristic'))} + optional CLIP visual",
            "seeds": seeds,
            "scoring": "build gate → per-feature sandboxed e2e completeness → optional CLIP text-image "
            "visual styling → plan/trajectory judge. Missing visual or claim-evidence signals make the "
            "live composite unevaluable rather than receiving fabricated defaults.",
            "synapse": f"backend={planner.backend} ({backend_note}).",
            "note": "Live mode uses a real generation harness, then builds, serves, and probes the app "
            "inside a non-root, deny-egress Docker sandbox. Chat integration reaches a deterministic "
            "sandbox-local OpenAI-compatible stub; it does not measure model answer quality. Mock mode "
            "models outcomes and is synthetic, not eligible for competitive headlines.",
        },
        containment=(
            {
                "payloads_executed": 0,
                "generated_apps_executed": len(results),
                "mode": "sealed Docker (non-root, deny-egress)",
                "note": "Generated apps are built, served, and probed only inside the resource-bounded "
                "sandbox. Infrastructure failures are recorded as skipped and excluded from scoring.",
            }
            if config.get("live")
            else {
                "payloads_executed": 0,
                "mode": "no-execution (synthetic)",
                "note": "No generated app is built or run; outcomes are modeled and non-competitive.",
            }
        ),
        skipped=list(skipped),
    )
