"""Track P orchestrator: build the storefront per harness (mock or sandboxed-live), score, RunRecord.

Defaults to seeds=1 — a single full-repo build is very costly (especially live with Cortex+Synapse).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path

from ..enums import Track
from ..models import SCHEMA_VERSION, RunRecord
from ..synapse import synapse_available
from .corpus import load_project_brief
from .models import ProjectResult
from .score import score_project

DEFAULT_PROJECT_HARNESSES = ("codex_cli_raw", "opencode", "omp", "claude_code", "cortex_wrapped", "cortex_omp", "cortex_claude")


_SIG_NAMES = ("build", "functional", "vertex", "pwa_a11y", "visual", "code_arch",
              "robustness", "code_health", "security", "ux", "composite")
_REL_K_P = 5  # report pass^1..pass^k reliability over seeds


def _project_reliability(rows: list[ProjectResult]) -> dict:
    """pass^k over seeds for one harness: a seed 'succeeds' iff it built and cleared the composite gate."""

    from ..scoring.stats import pass_hat_k

    n = len(rows)
    c = sum(1 for r in rows if r.signals.build and r.signals.functional >= 0.999)
    ks = list(range(1, min(_REL_K_P, n) + 1))
    return {"k": ks, "pass_hat_k": [round(pass_hat_k(n, c, k), 4) for k in ks],
            "success_rate": round(c / n, 4) if n else 0.0, "n_seeds": n}


def aggregate_project(results: list[ProjectResult], harnesses: list, *, basis: str = "") -> dict:
    """Per-harness signal vectors (mean over seeds) + pass^k reliability + a raw-vs-cortex delta."""

    from ..scoring.stats import mean
    by_h: dict[str, list[ProjectResult]] = {}
    for r in results:
        by_h.setdefault(r.harness_id, []).append(r)
    per_harness: dict[str, dict] = {}
    for hid, rows in by_h.items():
        if len(rows) == 1:  # seeds=1 (the default): byte-identical to the single-seed signal vector
            agg = dataclasses.asdict(rows[0].signals)
        else:
            sigs = [dataclasses.asdict(r.signals) for r in rows]
            agg = {k: round(mean([s[k] for s in sigs]), 4) for k in _SIG_NAMES}
        agg["reliability"] = _project_reliability(rows)
        per_harness[hid] = agg
    raw = next((h.id for h in harnesses if h.role == "raw"), None)
    cortex = next((h.id for h in harnesses if h.role == "cortex_wrapped"), None)
    delta: dict = {}
    if raw in per_harness and cortex in per_harness:
        rc, cc = per_harness[raw], per_harness[cortex]
        delta = {"raw": raw, "cortex_wrapped": cortex, "synapse": cortex, "basis": basis,
                 "composite": {"raw": rc["composite"], "cortex_wrapped": cc["composite"],
                               "delta": round(cc["composite"] - rc["composite"], 4)},
                 "functional": {"delta": round(cc["functional"] - rc["functional"], 4)},
                 "vertex": {"delta": round(cc["vertex"] - rc["vertex"], 4)}}
    return {"per_harness": per_harness, "synapse_delta": delta,
            "vertex_qe": _vertex_qe_block(results, per_harness),
            "signals": ["build", "functional", "vertex", "pwa_a11y", "visual", "code_arch",
                        "robustness", "code_health", "security", "ux", "composite"]}


def _vertex_qe_block(results: list[ProjectResult], per_harness: dict) -> dict:
    """VERTEX-QE over the arm pool (consensus + brief/repo estimated references) and its rank-correlation
    with authored VERTEX — the reference-free validation signal, persisted per run so the site can pool
    (authored, qe) pairs ACROSS runs/briefs into a stronger correlation (a single brief is indicative,
    not conclusive). Attaches `vertex_qe` to each harness. Never raises — an estimator hiccup must not
    break the aggregate."""

    try:
        from ..bootstrap import app_files
        from .corpus import load_project_brief
        from .models import Candidate
        from .validate_vertexqe import _spearman, _vertex_authored
        from .vertexqe import score_pool

        built = {}  # one candidate per harness (first built result), reconstructed from the persisted trajectory
        for r in results:
            if r.signals.build and r.harness_id not in built:
                # score the app-filtered view — the same view production scoring uses (score.py) — so
                # neither side of the (authored, qe) pair sees scaffolding the composite never scored
                built[r.harness_id] = Candidate(harness_id=r.harness_id, built=True, served=True,
                                                files=app_files(r.files), capabilities=list(r.capabilities),
                                                module_descriptors=list(r.module_descriptors))
        if len(built) < 1:
            return {"n_arms": 0, "note": "no built arms to score"}
        brief = load_project_brief()
        cands = list(built.values())
        qe = {row["harness_id"]: row["vertex_qe"] for row in score_pool(brief, cands)}
        # compute the authored side EXPLICITLY against the authored reference descriptors — the run's
        # own per_harness["vertex"] may have been scored in QE mode (live/rescore `auto` → qe), and
        # reusing it would make spearman_vs_authored a near-tautological QE-vs-QE comparison
        authored = {hid: _vertex_authored(brief, built[hid]) for hid in qe if hid in built}
        for hid, v in qe.items():  # surface the estimated-reference score beside authored VERTEX per harness
            if hid in per_harness:
                per_harness[hid]["vertex_qe"] = v
        hids = sorted(authored)
        pairs = [{"harness_id": h, "authored": authored[h], "qe": qe[h]} for h in hids]
        return {"n_arms": len(hids), "per_harness": {h: qe[h] for h in hids},
                "pairs": pairs,  # (authored, qe) per arm — the site pools these across runs to accumulate
                "spearman_vs_authored": _spearman([authored[h] for h in hids], [qe[h] for h in hids])}
    except Exception as exc:  # noqa: BLE001 — the estimator is additive; never break the run record
        return {"n_arms": 0, "error": f"vertex-qe unavailable: {exc}"}


def run_project_suite(
    harness_ids: tuple[str, ...] = DEFAULT_PROJECT_HARNESSES,
    run_id: str | None = None, live: bool = False, provider: str = "codex", seeds: int = 1,
    only: tuple[str, ...] = (), limit: int = 0, network_policy: str = "none",
    vision_judge: str = "heuristic", synapse_iterations: int = 3, out_dir: Path | None = None,
    vertex_ref: str = "auto",
) -> RunRecord:
    from ..analysis.embedding import warm
    from ..analysis.vertex import resolve_model
    from ..run import PRESETS, select_items
    from .judge import build_project_judges
    from .vertexqe import resolve_ref_mode

    if live and seeds != 1:
        raise ValueError("Live project execution supports exactly one seed per run")
    brief = load_project_brief()
    # Load the VERTEX embedding model ONCE, up front — before the concurrent cells spawn their subprocess
    # storm. A heavy first load under peak pressure hit torch EAGAIN, which was misread as a transient
    # fd-race and silently degraded VERTEX to 0 for every arm. Warming here surfaces a genuinely missing
    # model loudly, at a clean point, and means in-loop scoring only reuses the cached model.
    warm(resolve_model())
    judges = build_project_judges(vision_judge, live=live)  # raises on an unavailable/incompatible request
    resolved_vertex_ref = resolve_ref_mode(vertex_ref, live=live)
    if live:
        results, harnesses, skipped = _run_live(
            brief, provider, network_policy, judges,
            synapse_iterations=synapse_iterations, out_dir=out_dir,
            vertex_ref=resolved_vertex_ref,
        )
    else:
        skipped = []
        from .mock import mock_candidate

        metas = select_items([PRESETS[h] for h in harness_ids], only, limit, lambda m: m.id)
        harnesses = metas
        results = [score_project(brief, mock_candidate(brief, m, seed=s), judges, sandbox_backend="mock",
                                 vertex_ref=resolved_vertex_ref)
                   for m in metas for s in range(max(1, seeds))]
    return build_project_record(
        brief, results, harnesses, run_id=run_id, live=live, provider=provider,
        judge_backend=judges.backend, seeds=max(1, seeds),
        vertex_ref=resolved_vertex_ref, skipped=skipped,
    )


def _run_live(brief, provider: str, network_policy: str, judges, *,
              synapse_iterations: int = 3, out_dir: Path | None = None,
              vertex_ref: str | None = None):
    """Live: a real harness builds the repo (Synapse-wrapped arms plan + iterate), the Docker sandbox
    executes it once, the configured judge scores it."""

    from ..errors import EvaluationUnavailable, HarnessSetupError, HarnessTimeout
    from ..livegen.adapters import provider_harness_id
    from ..run import PRESETS
    from .sandbox import score_passes
    from .synapse_build import generate_repo, score_with_sandbox_repairs

    results, harnesses, skipped = [], [], []
    for prov in (p.strip() for p in provider.split(",") if p.strip()):
        meta = PRESETS[provider_harness_id(prov)]
        try:
            files, snapshots = generate_repo(
                brief, prov, meta, iterations=synapse_iterations,
                run_dir=out_dir, emit=lambda text: print(text, end=""),
            )
        except (HarnessTimeout, HarnessSetupError) as exc:
            skipped.append({"item": brief.id, "harness": meta.label, "reason": str(exc)})
            continue
        try:
            if meta.uses_synapse:
                result = score_with_sandbox_repairs(
                    brief, prov, meta, files, snapshots or [files],
                    iterations=synapse_iterations, run_dir=out_dir,
                    network_policy=network_policy, judges=judges, vertex_ref=vertex_ref,
                )
            else:
                result = score_passes(
                    brief, snapshots or [files], harness_id=meta.id, run_dir=out_dir,
                    network_policy=network_policy, judges=judges, vertex_ref=vertex_ref,
                )
        except EvaluationUnavailable as exc:
            skipped.append({"item": brief.id, "harness": meta.label, "reason": str(exc)})
            continue
        results.append(result)
        harnesses.append(meta)
    return results, harnesses, skipped


def build_project_record(
    brief, results: list[ProjectResult], harnesses, *,
    run_id: str | None, live: bool, provider: str,
    judge_backend: str = "heuristic-proxy", seeds: int = 1,
    vertex_ref: str = "authored", skipped=(),
) -> RunRecord:
    from ..run import new_run_id

    backend_note = "real synapse package installed" if synapse_available() else "offline shim"
    executed = any(r.sandbox_backend == "docker" for r in results)
    mode = "docker-sandboxed" if executed else ("docker-unavailable (not executed)" if live else "no-execution")
    basis = "measured (real harness build + sandbox execution)" if live else "mock (modelled long-horizon outcome)"
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        run_id=run_id or new_run_id("project"),
        created_at=datetime.now().isoformat(timespec="seconds"),
        track=Track.PROJECT,
        config={"suite": "project", "brief": brief.id, "harnesses": [h.id for h in harnesses],
                "judge": judge_backend, "seeds": seeds, "live": live, "basis": basis,
                "provider": provider if live else None, "vertex_ref": vertex_ref},
        harnesses=harnesses,
        cases=[{"id": brief.id, "title": brief.title, "prompt": brief.prompt,
                "screenshots": brief.screenshots,
                "capability_descriptors": brief.capability_descriptors}],
        results=results,
        aggregates=aggregate_project(results, harnesses, basis=basis),
        methodology={
            "judge_model": judge_backend,  # the backend that ACTUALLY produced the visual/arch/ux signals
            "signals": "gated composite over objective (build/functional-e2e/pwa-a11y/code-health/"
            "robustness/security), VERTEX capability+architecture cross-similarity (cosine + DTW "
            "distance-decay, chance-normalized), and the visual/code-arch/ux judge.",
            "vertex": "VERTEX capability and architecture cross-similarity; VERTEX-QE estimates "
            "semantic inter-source agreement and proportionally down-weights uncertain architecture "
            "references. Live auto resolves to QE; mock auto keeps authored fixtures stable.",
            "synapse": f"backend={backend_note}; bounded generation/repair, not a closure guarantee.",
            "note": f"basis={basis}. Live mode builds the repo with a real harness and executes it in a "
            "hardened Docker sandbox (non-root, deny-egress, resource-limited) with Playwright capture; "
            f"judge={judge_backend} scores fidelity vs the reference frames. Mock models the long-horizon "
            "outcome (heuristic-proxy judge only — no real renders). seeds=1 (a full-repo build is costly).",
        },
        containment={
            "payloads_executed": 0,
            "mode": mode,
            "note": "Untrusted generated apps run only in an ephemeral, non-root, deny-egress container "
            "with CPU/mem/pid/time limits; never on the host.",
        },
        skipped=list(skipped),
    )
