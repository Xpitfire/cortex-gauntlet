"""CLI for the Gauntlet benchmark.

    python -m gauntlet run [--adapters a,b] [--judge auto|heuristic|cortex|claude] [--seeds N] [--held-out]
    python -m gauntlet run --track project [--live --provider codex] [--vision-judge …] [--vertex-ref …]
    python -m gauntlet suite --tracks project,generative,repo --tui --live --provider codex,omp,claude,cortex
    python -m gauntlet rescore <run> [--tracks all] [--judge …] [--vision-judge …]  # re-score persisted artifacts, no re-gen
    python -m gauntlet report  <run-id>
    python -m gauntlet compare <run-id-a> <run-id-b>

`--judge auto` uses the direct Claude semantic judge for live judged tracks, else the offline heuristic.
`--vision-judge auto` picks the real CLIP vision judge under --live, else the heuristic proxy.
`--vertex-ref auto` uses VERTEX-QE for live Project runs, authored references for mock fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .analysis.embedding import EmbeddingUnavailable
from .generative import run_generative_suite
from .project.judge import JudgeUnavailable
from .paths import RESULTS
from .project.vertexqe import VERTEX_REF_CHOICES
from .quality import run_quality_suite
from .report import build_report
from .run import new_run_id, resolve_track_judge, run_suite, security_adapter_specs

_COMPARE_METRICS = ("asr", "over_refusal", "utility_under_attack")


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "unavailable"


def _print_summary(record: dict) -> None:
    track = record["track"]
    track = getattr(track, "value", track)
    seeds = record["config"].get("seeds", 1)
    print(f"\nGauntlet run {record['run_id']}  ({track})")
    print(f"  cases: {len(record['cases'])}   results: {len(record['results'])}   attempts/case: {seeds}")
    print("  LIVE observations" if record["config"].get("live")
          else "  SYNTHETIC modeled run — not measured performance")
    print(f"  containment: payloads_executed={record['containment']['payloads_executed']}")
    print("  ASR (LOWER safer) [iid Wilson reference CI] · any-seed = attack-success@n")
    for hid, m in record["aggregates"]["per_harness"].items():
        asr, ci = m["asr"]["rate"], m["asr"]["ci"]
        print(
            f"  {hid:<16} ASR {_pct(asr)} [{_pct(ci[0])}-{_pct(ci[1])}]"
            f"  any-seed {_pct(m['asr_at_n'])}  over-ref {_pct(m['over_refusal']['rate'])}"
            f"  util {_pct(m['utility_under_attack']['rate'])}"
        )
        if record["config"].get("security_passes", 1) > 1:
            turns = "  ".join(f"p{p['pass']} {_pct(p['asr']['rate'])}"
                              for p in m.get("security_passes", []))
            print(f"    adaptive ASR by pass: {turns}")
    delta = record["aggregates"].get("harness_delta", {})
    if delta.get("asr", {}).get("delta") is not None:
        pts = delta["asr"]["delta"] * 100
        verdict = (
            f"cuts attack success by {pts:.1f} pts vs raw — safer"
            if pts >= 0 else f"is {abs(pts):.1f} pts WORSE than raw"
        )
        print(f"  -> Cortex {verdict}")


def _print_repo_summary(record: dict) -> None:
    basis = record.get("config", {}).get("basis", "")
    print(f"\nGauntlet run {record['run_id']}  (repo · {basis})")
    print(f"  issues: {len(record['cases'])}   results: {len(record['results'])}")
    print("  resolution = hidden test that failed on the base repo passes after the arm's patch [Wilson CI]")
    for hid, m in record["aggregates"]["per_harness"].items():
        err = f"  errors {m['errors']}" if m.get("errors") else ""
        print(f"  {hid:<16} resolved {m['resolved']}/{m['n']}  rate {m['resolution_rate'] * 100:5.1f}%"
              f"  [{m['ci'][0] * 100:4.1f}-{m['ci'][1] * 100:4.1f}]{err}")
    d = record["aggregates"].get("synapse_delta", {}).get("resolution_rate", {})
    if d:
        pts = d["delta"] * 100
        print(f"  -> Cortex resolution {'+' if pts >= 0 else ''}{pts:.1f} pts vs raw")


def _print_quality_summary(record: dict) -> None:
    print(f"\nGauntlet run {record['run_id']}  (quality)")
    print(f"  tasks: {len(record['cases'])}   results: {len(record['results'])}")
    print(f"  {record['methodology']['synapse']}")
    print("  functional = real pytest pass-rate (Bandit static + pytest dynamic); higher coverage/functional better")
    for hid, m in record["aggregates"]["per_harness"].items():
        fn = m.get("functional_rate")
        fn_s = f"{fn * 100:5.1f}%" if fn is not None else "  n/a"
        print(
            f"  {hid:<16} grade {m['maintainability']['grade']}  coverage {m['requirement_coverage'] * 100:5.1f}%"
            f"  functional {fn_s}  vulns/task {m['vulns_per_task']:.2f}  debt {m['maintainability']['debt']:.2f}"
        )
    d = record["aggregates"].get("synapse_delta", {})
    if d.get("synapse"):
        print(f"  -> Synapse lifts coverage +{d['requirement_coverage']['delta'] * 100:.1f} pts, functional "
              f"+{d['functional_rate']['delta'] * 100:.1f} pts, cuts {d['vulns_per_task']['delta']:.2f} vulns/task vs raw")


def _print_generative_summary(record: dict) -> None:
    print(f"\nGauntlet run {record['run_id']}  (generative)")
    print(f"  apps: {len(record['cases'])}   results: {len(record['results'])}   "
          f"features: {record['aggregates']['feature_count']}   seeds: {record['config']['seeds']}")
    print("  LIVE observations" if record["config"].get("live")
          else "  SYNTHETIC modeled run — not measured performance")
    print(f"  {record['methodology']['synapse']}")
    print("  completeness = features delivered & passing e2e (higher better)")
    for hid, m in record["aggregates"]["per_harness"].items():
        if not m["evaluable"]:
            degraded = ", ".join(m["degraded"]) or "unavailable"
            print(f"  {hid:<16} UNEVALUABLE ({degraded})")
            continue
        print(
            f"  {hid:<16} completeness {m['completeness'] * 100:5.1f}%  build {m['build_rate'] * 100:5.1f}%"
            f"  plan {m['plan']:.2f}  honesty {m['honesty'] * 100:5.1f}%  composite {m['g_score']:.3f}"
        )
    d = record["aggregates"].get("synapse_delta", {})
    if d.get("synapse") and d["g_score"]["delta"] is not None:
        print(f"  -> Governed-minus-raw feature completeness {d['completeness']['delta'] * 100:+.1f} pts "
              f"and composite {d['g_score']['delta']:+.3f}; not a causal attribution")
    if record.get("skipped"):
        print(f"  skipped infrastructure cells: {len(record['skipped'])}")


def _print_project_summary(record: dict) -> None:
    print(f"\nGauntlet run {record['run_id']}  (project)")
    print(f"  brief: {record['cases'][0]['title']}   harnesses: {len(record['harnesses'])}   "
          f"seeds: {record['config']['seeds']}   sandbox: {record['containment']['mode']}")
    print("  composite = build-gated weighted sum of objective + VERTEX + judge signals (higher better)")
    for hid, s in record["aggregates"]["per_harness"].items():
        print(
            f"  {hid:<16} build {('✓' if s['build'] else '✗')}  functional {s['functional'] * 100:5.1f}%"
            f"  VERTEX {s['vertex'] * 100:5.1f}%  visual {s['visual'] * 100:5.1f}%"
            f"  code/arch {s['code_arch'] * 100:5.1f}%  composite {s['composite'] * 100:5.1f}%"
        )
    d = record["aggregates"].get("synapse_delta", {})
    if d.get("composite"):
        print(f"  -> Cortex composite +{d['composite']['delta'] * 100:.1f} pts vs raw "
              f"(VERTEX +{d['vertex']['delta'] * 100:.1f}, functional +{d['functional']['delta'] * 100:.1f})")


def _subset(args: argparse.Namespace) -> tuple[tuple[str, ...], int]:
    only = tuple(s.strip() for s in args.only.split(",") if s.strip())
    return only, args.limit


def _live_providers(provider: str) -> str | None:
    """Preflight the requested live providers: print readiness, drop un-runnable arms with their fix,
    and return the runnable comma-list (None if none are runnable — the caller should abort)."""
    from .preflight import check_providers

    requested = [p.strip() for p in provider.split(",") if p.strip()]
    readiness = check_providers(requested)
    runnable = []
    print("  provider readiness:")
    for r in readiness:
        print(f"    {'✓' if r.ok else '✗'} {r.provider:18} {r.reason}")
        if r.ok:
            runnable.append(r.provider)
        elif r.remedy:
            print(f"        ↳ fix: {r.remedy}")
    if not runnable:
        print("  no runnable providers — aborting.", file=sys.stderr)
        return None
    if len(runnable) < len(requested):
        print(f"  running: {','.join(runnable)}  (skipped the un-runnable arms above)")
    return ",".join(runnable)


def _apply_rate_limit_policy(args: argparse.Namespace) -> None:
    """A `--rate-limit-retries` flag overrides the smart default for this process; print the effective
    policy on live runs so the wait-vs-pause behaviour is visible up front."""
    n = getattr(args, "rate_limit_retries", None)
    if n is not None:
        os.environ["GAUNTLET_RATELIMIT_RETRIES"] = str(max(0, n))
    if getattr(args, "live", False):
        from .resilience import backoff_delays, rate_limit_retries

        retries = rate_limit_retries()
        budget = int(sum(backoff_delays(retries)))
        policy = (f"up to {retries} retries (~{budget}s backoff) then pause + checkpoint"
                  if retries else "pause + checkpoint immediately (no backoff)")
        print(f"  rate-limit policy: {policy}")


def _execute_track(
    track: str, *, run_id: str, out_dir, live: bool, provider: str, judge: str, seeds: int,
    held_out: bool, suite: str, adapters: str, only: tuple[str, ...], limit: int,
    network_policy: str, vision_judge: str, synapse_iterations: int, vertex_ref: str,
    security_passes: int = 1, red_team: str = "auto",
):
    """Run one track end-to-end: build the record, write runrecord.json + report.html, print the
    per-track summary, and return the record. Shared by `run` (one track) and `suite` (all tracks)."""

    judge = resolve_track_judge(track, judge, live)

    if track == "repo":
        from .repo import run_repo_suite

        record = run_repo_suite(run_id=run_id, live=live, provider=provider, only=only, limit=limit,
                                seeds=seeds, judge_name=judge)
        printer = _print_repo_summary
    elif track == "project":
        from .project import run_project_suite
        from .project.corpus import copy_reference_screenshots

        record = run_project_suite(run_id=run_id, live=live, provider=provider, only=only, limit=limit,
                                   network_policy=network_policy, vision_judge=vision_judge,
                                   synapse_iterations=synapse_iterations, out_dir=out_dir,
                                   vertex_ref=vertex_ref)
        copy_reference_screenshots(out_dir)  # reference frames beside the report (idempotent)
        printer = _print_project_summary
    elif track == "quality":
        record = run_quality_suite(judge_name=judge, run_id=run_id, live=live, provider=provider,
                                   only=only, limit=limit, seeds=seeds)
        printer = _print_quality_summary
    elif track == "generative":
        record = run_generative_suite(seeds=seeds, judge_name=judge, run_id=run_id,
                                      assets_dir=out_dir / "assets", live=live, provider=provider,
                                      only=only, limit=limit)
        printer = _print_generative_summary
    else:  # security — --live maps the provider list to live adapters (else mock DEFAULT_ADAPTERS)
        specs = security_adapter_specs(live=live, provider=provider, adapters=adapters)
        record = run_suite(suite=suite, adapter_specs=specs, judge_name=judge, seeds=seeds,
                           include_held_out=held_out, run_id=run_id, assets_dir=out_dir / "assets",
                           only=only, limit=limit, security_passes=security_passes,
                           red_team_name=red_team)
        printer = _print_summary
    (out_dir / "runrecord.json").write_text(record.to_json())
    build_report(json.loads(record.to_json()), out_dir / "report.html")
    printer(record.to_dict())
    print(f"  runrecord: {out_dir / 'runrecord.json'}   report: {out_dir / 'report.html'}")
    return record


def cmd_run(args: argparse.Namespace) -> int:
    if args.track == "bugfix":  # user-facing alias for the stable track id "repo" (SWE-bench-style)
        args.track = "repo"
    label = args.track if args.track in ("quality", "generative", "project", "repo") else args.suite
    run_id = new_run_id(label)
    out_dir = RESULTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    only, limit = _subset(args)
    _apply_rate_limit_policy(args)
    if args.live:  # fail fast: preflight the providers and drop un-runnable arms with their fix
        provider = _live_providers(args.provider)
        if provider is None:
            return 1
        args.provider = provider
    _execute_track(args.track, run_id=run_id, out_dir=out_dir, live=args.live, provider=args.provider,
                   judge=args.judge, seeds=args.seeds, held_out=args.held_out, suite=args.suite,
                   adapters=args.adapters, only=only, limit=limit, network_policy=args.network_policy,
                   vision_judge=args.vision_judge, synapse_iterations=args.synapse_iterations,
                   vertex_ref=args.vertex_ref, security_passes=args.security_passes,
                   red_team=args.red_team)
    if not args.no_site:
        # rebuild the navigable site (summary + Docs + every track report, cross-linked) and point
        # the user there — the standalone report above has no working cross-track navigation.
        from .site import build_site
        dist = build_site()
        print(f"\n  ▶ open the navigable site (all tracks + Docs):\n    {dist / 'index.html'}\n"
              "    (skip this rebuild with --no-site)\n")
    return 0


# Track order + per-track seed policy for the full suite. Security/Quality/Bugfix take `--seeds`
# (worst-of-N, default 3: any seed failing = fail); Generative and Project always run once — a full
# app/repo build per seed is too costly.
_SUITE_TRACKS = ("security", "quality", "generative", "project", "repo")


def cmd_suite(args: argparse.Namespace) -> int:
    """Run every track once with sensible per-track defaults, then build the aggregated site."""

    _apply_rate_limit_policy(args)
    if getattr(args, "keep_containers", False):  # keep project apps served per-port for qualitative review
        os.environ["GAUNTLET_KEEP_CONTAINERS"] = "1"
    if args.live:  # preflight once; abort cheaply if no arm is runnable
        provider = _live_providers(args.provider)
        if provider is None:
            return 1
        args.provider = provider
    tracks = [("repo" if t.strip() == "bugfix" else t.strip())  # "bugfix" → stable id "repo"
              for t in args.tracks.split(",") if t.strip()]
    # --seeds repeats (worst-of-N: any seed failing = fail) apply to the non-deterministic live tracks;
    # the expensive build tracks always run once.
    seeds_for = {"security": args.seeds, "quality": args.seeds, "repo": args.seeds,
                 "generative": 1, "project": 1}
    tui_tracks = {"security", "quality", "generative", "project", "repo"}  # all have TUI cell builders
    mode = f"live · {args.provider}" if args.live else "mock"
    print(f"\nGauntlet SUITE  ({mode}{', unified TUI' if args.tui else ', headless'})"
          f"\n  tracks: {', '.join(tracks)}"
          f"\n  seeds: security/quality/repo={args.seeds} (worst-of-N), generative=1, project=1\n")
    # With --tui the TUI-capable tracks run in ONE Textual app (a section per track); repo and any
    # non-TUI track run headless. Without --tui everything runs headless.
    resume_dir = None
    if getattr(args, "resume", ""):
        resume_dir = Path(args.resume) if "/" in args.resume else RESULTS / args.resume
        if not (resume_dir / "checkpoint.jsonl").exists():
            print(f"no checkpoint.jsonl to resume under {resume_dir}", file=sys.stderr)
            return 1
        print(f"  ▶ resuming suite from {resume_dir.name} (only not-yet-done cells will run)\n")
    if args.tui:
        from .tui import run_suite_tui

        in_tui = [t for t in tracks if t in tui_tracks]
        if in_tui:
            print(f"  ▶ opening one TUI for: {', '.join(in_tui)}\n")
            run_suite_tui(in_tui, live=args.live, provider=args.provider, seeds_for=seeds_for,
                          network_policy=args.network_policy, vision_judge=args.vision_judge,
                          synapse_iterations=args.synapse_iterations, judge=args.judge,
                          resume_dir=resume_dir, vertex_ref=args.vertex_ref,
                          security_passes=args.security_passes, red_team=args.red_team,
                          workers=args.workers)
        headless = [t for t in tracks if t not in tui_tracks]
    else:
        headless = tracks
    for track in headless:
        label = track if track in ("quality", "generative", "project", "repo") else "security"
        seeds = seeds_for.get(track, 1)
        print(f"{'=' * 64}\n  SUITE · {track}  (seeds={seeds})\n{'=' * 64}")
        run_id = new_run_id(label)
        out_dir = RESULTS / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        _execute_track(track, run_id=run_id, out_dir=out_dir, live=args.live, provider=args.provider,
                       judge=args.judge, seeds=seeds, held_out=False,
                       suite="security", adapters="", only=(), limit=0,
                       network_policy=args.network_policy, vision_judge=args.vision_judge,
                       synapse_iterations=args.synapse_iterations, vertex_ref=args.vertex_ref,
                       security_passes=args.security_passes, red_team=args.red_team)
    if not args.no_site:
        from .site import build_site

        dist = build_site()
        print(f"\n  ▶ full suite done — navigable site (all tracks + Docs):\n    {dist / 'index.html'}\n")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    record_path = RESULTS / args.run_id / "runrecord.json"
    if not record_path.exists():
        print(f"no runrecord at {record_path}", file=sys.stderr)
        return 1
    build_report(json.loads(record_path.read_text()), RESULTS / args.run_id / "report.html")
    print(f"report: {RESULTS / args.run_id / 'report.html'}")
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    """Ask a running suite/track to pause gracefully AFTER its current cell — it checkpoints that cell
    first, so nothing fails. Resume later with `--resume <run-id>`. Works from another terminal (e.g.
    before unplugging / moving the laptop): it drops a PAUSE sentinel the runner watches between cells."""

    run_dir = Path(args.run) if "/" in args.run else RESULTS / args.run
    if not run_dir.exists():
        print(f"no run dir at {run_dir}", file=sys.stderr)
        return 1
    (run_dir / "PAUSE").write_text("paused by user\n", encoding="utf-8")
    print(f"pause requested for {run_dir.name} — it will stop after the current cell (already-done "
          f"cells are saved).\n  resume with:  cortex benchmark suite --resume {run_dir.name} "
          f"--live --provider <list>")
    return 0


def cmd_rescore(args: argparse.Namespace) -> int:
    """Re-score a finished run (or the latest run of each selected track) from PERSISTED artifacts with
    the current scoring — no harness re-generation. The configured judge/vision-judge ARE used."""

    from .rescore_tracks import rescore

    tracks: tuple[str, ...] = ()
    if args.tracks.strip().lower() == "all":
        tracks = ("project", "quality", "repo", "generative", "security")
    elif args.tracks:
        tracks = tuple(t.strip() for t in args.tracks.split(",") if t.strip())
    out = rescore(run=args.run, tracks=tracks, judge=args.judge, vision_judge=args.vision_judge,
                  vertex_ref=args.vertex_ref, in_place=args.in_place)
    if not out:
        print("nothing to re-score — give a run dir or --tracks (no matching run found)", file=sys.stderr)
        return 1
    for track, s in out.items():
        if s.get("error"):
            print(f"  {track}: {s['error']}")
        else:
            report = s.get("paths", {}).get("report", "(no report)")
            print(f"  {track}: re-scored {s.get('rescored', 0)} cells (judge={args.judge}"
                  f"{', vision=' + args.vision_judge if track == 'project' else ''}"
                  f"{', vertex-ref=' + args.vertex_ref if track == 'project' else ''}) → {report}")
    if not args.no_site:
        from .site import build_site
        dist = build_site()
        print(f"\n  ▶ open the navigable site (all tracks):\n    {dist / 'index.html'}\n")
    return 0


def cmd_retry_timeouts(args: argparse.Namespace) -> int:
    """Reload a completed run and re-run ONLY its timed-out cells, then patch the record in place."""

    from .run import retry_security_timeouts

    run_dir = Path(args.run_dir) if "/" in args.run_dir else RESULTS / args.run_dir
    record_path = run_dir / "runrecord.json"
    if not record_path.exists():
        print(f"no runrecord at {record_path}", file=sys.stderr)
        return 1
    record = json.loads(record_path.read_text())
    track = record.get("track")
    if track != "security":
        print(f"retry-timeouts currently supports the security track (this record is '{track}').",
              file=sys.stderr)
        return 1
    # re-runs with the SAME adapters the run recorded (live or mock); the missing cells are re-run live
    # when the record is a live run. A cell that times out again stays skipped.
    rebuilt, retried_ok, still = retry_security_timeouts(record)
    record_path.write_text(rebuilt.to_json(), encoding="utf-8")
    build_report(rebuilt.to_dict(), run_dir / "report.html")
    print(f"  ▶ {run_dir.name}: retried {retried_ok} timed-out cell(s), {still} still skipped\n"
          f"    record + report patched: {record_path}")
    if not args.no_site:
        from .site import build_site
        print(f"    site rebuilt: {build_site() / 'index.html'}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    runs = {}
    for run_id in (args.run_a, args.run_b):
        path = RESULTS / run_id / "runrecord.json"
        if not path.exists():
            print(f"no runrecord at {path}", file=sys.stderr)
            return 1
        runs[run_id] = json.loads(path.read_text())
    a, b = runs[args.run_a], runs[args.run_b]
    pa, pb = a["aggregates"]["per_harness"], b["aggregates"]["per_harness"]
    shared = [h for h in pa if h in pb]
    comparison = {"run_a": args.run_a, "run_b": args.run_b, "harnesses": {}}
    print(f"\nCompare {args.run_a}  vs  {args.run_b}   (delta = A - B; metric rates)")
    for hid in shared:
        row = {}
        print(f"  {hid}")
        for metric in _COMPARE_METRICS:
            ra, rb = pa[hid][metric]["rate"], pb[hid][metric]["rate"]
            difference = ra - rb if ra is not None and rb is not None else None
            row[metric] = {
                "a": round(ra, 4) if ra is not None else None,
                "b": round(rb, 4) if rb is not None else None,
                "delta": round(difference, 4) if difference is not None else None,
            }
            print(f"    {metric:<20} A {_pct(ra)}   B {_pct(rb)}   Δ {_pct(difference)}")
        comparison["harnesses"][hid] = row
    out = RESULTS / f"compare-{args.run_a}-vs-{args.run_b}.json"
    out.write_text(json.dumps(comparison, indent=2))
    print(f"\n  comparison: {out}\n")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from .tui import run_tui

    if args.track == "bugfix":  # user-facing alias for the stable track id "repo" (SWE-bench-style)
        args.track = "repo"
    _apply_rate_limit_policy(args)
    if args.load:
        run_tui(args.track, load=args.load, force_console=args.no_tui)
        return 0
    if args.resume:  # resume a paused run from its checkpoint (re-runs only the not-yet-done cells)
        run_dir = Path(args.resume) if "/" in args.resume else RESULTS / args.resume
        if not run_dir.exists():
            print(f"no run dir to resume at {run_dir}", file=sys.stderr)
            return 1
        print(f"resuming {run_dir.name} from checkpoint")
    else:
        run_id = new_run_id(args.track if args.track in ("quality", "generative", "project", "repo") else args.suite)
        run_dir = RESULTS / f"tui-{run_id}"
    only, limit = _subset(args)
    if args.live:  # fail fast: preflight the providers and drop un-runnable arms with their fix
        provider = _live_providers(args.provider)
        if provider is None:
            return 1
        args.provider = provider
    run_tui(args.track, live=args.live, provider=args.provider, seeds=args.seeds,
            suite=args.suite, run_dir=run_dir, force_console=args.no_tui, only=only, limit=limit,
            network_policy=args.network_policy, vision_judge=args.vision_judge,
            synapse_iterations=args.synapse_iterations, judge=args.judge, vertex_ref=args.vertex_ref,
            security_passes=args.security_passes, red_team=args.red_team, workers=args.workers)
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    from .site import build_site

    dist = build_site()
    runs = len(list((dist / "runs").glob("*")))
    print(f"built public site: {dist / 'index.html'}  ({runs} runs)")
    print("  redeploy: cortex --profile <your-production-profile> deploy --manifest .cortex/benchmark.app.yml"
          " --ref <published-commit>   (public at https://benchmark.cortex.a2olabs.com/)")
    return 0


def main(argv: list[str] | None = None) -> int:
    from .analysis import _proc

    _proc.install_fork_lock()  # serialize fork/exec: the suite spawns analyzers from many cell threads at once
    parser = argparse.ArgumentParser(prog="gauntlet", description="Cortex Harness Benchmark")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a suite and build a report")
    run.add_argument("--track", default="security",
                     choices=["security", "quality", "generative", "project", "repo", "bugfix"])
    run.add_argument("--suite", default="security")
    run.add_argument("--adapters", default="", help="comma list, e.g. mock:codex_cli_raw,mock:opencode")
    run.add_argument("--judge", default="auto", choices=["auto", "heuristic", "cortex", "claude"],
                     help="auto = direct claude-CLI semantic judge for live judged tracks, heuristic otherwise")
    run.add_argument("--seeds", type=int, default=1, help="attempts per case (attempt budget)")
    run.add_argument("--held-out", action="store_true", help="include the private held-out split")
    run.add_argument("--live", action="store_true", help="generate code via a real harness CLI (needs auth)")
    run.add_argument("--rate-limit-retries", type=int, default=None,
                     help="retries to absorb a transient provider rate limit before pausing + "
                          "checkpointing (default 3 ≈ 35s backoff; 0 = pause immediately)")
    run.add_argument("--provider", default="codex",
                     help="live harness(es), comma-separated for a multi-harness comparison: "
                          "codex | omp | claude | opencode | cortex[:codex|omp|claude] "
                          "(e.g. codex,omp,cortex,cortex:omp)")
    run.add_argument("--only", default="",
                     help="run only these item ids (comma list), e.g. shop_cart,web_security_utils")
    run.add_argument("--limit", type=int, default=0, help="run only the first N items (0 = all)")
    run.add_argument("--no-site", action="store_true",
                     help="don't rebuild the navigable site after the run (write the report only)")
    run.add_argument("--network-policy", default="none", choices=["none", "stripe-test"],
                     help="Track P sandbox egress: 'none' denies all; 'stripe-test' allows only Stripe test hosts via the allowlist proxy")
    run.add_argument("--vision-judge", default="auto", choices=["auto", "heuristic", "clip", "claude-vision"],
                     help="Track P qualitative judge: 'heuristic' (offline proxy), 'clip' (local CLIP VLM), 'claude-vision' (LLM via the harness). clip/claude-vision require --live")
    run.add_argument("--vertex-ref", default="auto", choices=VERTEX_REF_CHOICES,
                     help="Track P VERTEX reference: auto = qe for live Project runs, authored for mock")
    run.add_argument("--synapse-iterations", type=int, default=3,
                     help="Track P: max Synapse plan→validate→repair passes for the cortex arm "
                          "(1 = plan once, no repair; the default 3 lets the loop repair gaps). "
                          "Each pass is another full repo build.")
    run.add_argument("--security-passes", type=int, default=1,
                     help="Track S adaptive adversarial user turns per seed; 1 keeps one-shot behavior")
    run.add_argument("--red-team", default="auto", choices=["auto", "heuristic", "claude"],
                     help="Track S follow-up generator; auto uses Claude for live semantic runs")
    run.set_defaults(func=cmd_run)

    suite = sub.add_parser("suite", help="run all tracks with per-track defaults, then build the site")
    suite.add_argument("--tracks", default=",".join(_SUITE_TRACKS),
                       help="comma list of tracks to run, in order")
    suite.add_argument("--live", action="store_true",
                       help="generate code via real harness CLIs (needs auth)")
    suite.add_argument("--provider", default="codex",
                       help="live harness(es), comma-separated, e.g. "
                            "codex,omp,claude,opencode,cortex,cortex:omp,cortex:claude")
    suite.add_argument("--seeds", type=int, default=3,
                       help="repeats for Security/Quality/Repo (default 3; worst-of-N: any seed "
                            "failing = fail); Generative and Project always run once")
    suite.add_argument("--tui", action="store_true",
                       help="follow all tracks in ONE Textual IDE (a section per track)")
    suite.add_argument("--judge", default="auto", choices=["auto", "heuristic", "cortex", "claude"],
                       help="auto = direct claude-CLI semantic judge for live judged tracks, heuristic otherwise")
    suite.add_argument("--network-policy", default="none", choices=["none", "stripe-test"],
                       help="Track P sandbox egress")
    suite.add_argument("--keep-containers", action="store_true",
                       help="Track P: keep each built app SERVED on its own host port (127.0.0.1) for "
                            "qualitative review; torn down when the TUI closes")
    suite.add_argument("--vision-judge", default="auto", choices=["auto", "heuristic", "clip", "claude-vision"],
                       help="Track P qualitative judge (clip/claude-vision require --live)")
    suite.add_argument("--vertex-ref", default="auto", choices=VERTEX_REF_CHOICES,
                       help="Track P VERTEX reference: auto = qe for live Project runs, authored for mock")
    suite.add_argument("--synapse-iterations", type=int, default=3,
                       help="Track P: max Synapse plan→validate→repair passes for the cortex arm "
                            "(1 = plan once, no repair; default 3)")
    suite.add_argument("--rate-limit-retries", type=int, default=None,
                       help="retries to absorb a transient provider rate limit before pausing")
    suite.add_argument("--security-passes", type=int, default=1,
                       help="Track S adaptive adversarial user turns per seed")
    suite.add_argument("--red-team", default="auto", choices=["auto", "heuristic", "claude"],
                       help="Track S follow-up generator")
    suite.add_argument("--workers", type=int, default=1,
                       help="concurrent provider arms (one thread per harness; each provider's cells "
                            "stay serial, different providers overlap). 1 = strictly serial (default); "
                            "set to the number of --provider arms for full parallelism")
    suite.add_argument("--no-site", action="store_true",
                       help="don't rebuild the navigable site after the suite")
    suite.add_argument("--resume", default="",
                       help="resume a suite run dir/run-id from its checkpoint (re-runs only the "
                            "not-yet-done cells; --tui only)")
    suite.set_defaults(func=cmd_suite)

    report = sub.add_parser("report", help="rebuild a report from a saved runrecord")
    report.add_argument("run_id")
    report.set_defaults(func=cmd_report)

    rescore = sub.add_parser(
        "rescore", help="re-score a finished run from PERSISTED artifacts with current scoring (ANY "
                        "track; no harness re-generation — the configured judges ARE used)")
    rescore.add_argument("run", nargs="?", default="",
                         help="a run dir / run-id under results/ (track auto-detected); omit to use --tracks")
    rescore.add_argument("--tracks", default="",
                         help="comma list project,quality,repo,generative,security — or 'all'. Re-scores "
                              "the LATEST run of each (ignored when a run is given)")
    rescore.add_argument("--judge", default="heuristic", choices=["heuristic", "cortex", "claude"],
                         help="judge backend used IN the re-score loop (security/quality LLM judge)")
    rescore.add_argument("--vision-judge", default="auto", choices=["auto", "heuristic", "clip", "claude-vision"],
                         help="project vision judge used IN the re-score loop (clip/claude-vision run on the "
                              "persisted screenshots)")
    rescore.add_argument("--vertex-ref", default="auto", choices=VERTEX_REF_CHOICES,
                         help="project VERTEX reference used IN the re-score loop; auto resolves to qe")
    rescore.add_argument("--no-site", action="store_true", help="don't rebuild the navigable site after")
    rescore.add_argument("--in-place", action="store_true",
                         help="overwrite the ORIGINAL run's runrecord/report with the corrected numbers "
                              "(so a reopened run shows them) instead of a non-destructive -rescored copy")
    rescore.set_defaults(func=cmd_rescore)

    pause = sub.add_parser(
        "pause", help="pause a running suite/track gracefully (checkpoints, then stops; resume later)")
    pause.add_argument("run", help="the run dir or run-id under results/ to pause")
    pause.set_defaults(func=cmd_pause)

    compare = sub.add_parser("compare", help="compare two runs by harness (delta view)")
    compare.add_argument("run_a")
    compare.add_argument("run_b")
    compare.set_defaults(func=cmd_compare)

    retry = sub.add_parser("retry-timeouts",
                           help="reload a completed run and re-run ONLY its timed-out cells, in place")
    retry.add_argument("run_dir", help="run dir or run-id under results/ whose runrecord.json to patch")
    retry.add_argument("--no-site", action="store_true", help="skip rebuilding the aggregated site")
    retry.set_defaults(func=cmd_retry_timeouts)

    site = sub.add_parser("site", help="build the aggregated public results site (site/public/)")
    site.set_defaults(func=cmd_site)

    tui = sub.add_parser("tui", help="run a track in the live experiment IDE (Textual TUI)")
    tui.add_argument("--track", default="security",
                     choices=["security", "quality", "generative", "project", "repo", "bugfix"])
    tui.add_argument("--suite", default="security")
    tui.add_argument("--judge", default="auto", choices=["auto", "heuristic", "cortex", "claude"],
                     help="auto = direct claude-CLI semantic judge for live judged tracks, heuristic otherwise")
    tui.add_argument("--seeds", type=int, default=1)
    tui.add_argument("--live", action="store_true", help="generate code via a real harness CLI (needs auth)")
    tui.add_argument("--provider", default="codex",
                     help="live harness(es), comma-separated (e.g. codex,omp,cortex,cortex:omp)")
    tui.add_argument("--only", default="",
                     help="run only these item ids (comma list), e.g. shop_cart,web_security_utils")
    tui.add_argument("--limit", type=int, default=0, help="run only the first N items (0 = all)")
    tui.add_argument("--network-policy", default="none", choices=["none", "stripe-test"],
                     help="Track P sandbox egress: 'none' denies all; 'stripe-test' allows only Stripe test hosts")
    tui.add_argument("--vision-judge", default="auto", choices=["auto", "heuristic", "clip", "claude-vision"],
                     help="Track P qualitative judge: heuristic|clip|claude-vision (clip/claude-vision require --live)")
    tui.add_argument("--vertex-ref", default="auto", choices=VERTEX_REF_CHOICES,
                     help="Track P VERTEX reference: auto = qe for live Project runs, authored for mock")
    tui.add_argument("--synapse-iterations", type=int, default=3,
                     help="Track P: max Synapse plan→validate→repair passes for the cortex arm "
                          "(1 = plan once, no repair; the default 3 lets the loop repair gaps). "
                          "Each pass is another full repo build.")
    tui.add_argument("--no-tui", action="store_true", help="force the plain console observer (no Textual)")
    tui.add_argument("--resume", default="",
                     help="resume a paused run by its dir/run-id (re-runs only the not-yet-done cells)")
    tui.add_argument("--rate-limit-retries", type=int, default=None,
                     help="retries to absorb a transient provider rate limit before pausing + "
                          "checkpointing (default 3 ≈ 35s backoff; 0 = pause immediately)")
    tui.add_argument("--security-passes", type=int, default=1,
                     help="Track S adaptive adversarial user turns per seed")
    tui.add_argument("--red-team", default="auto", choices=["auto", "heuristic", "claude"],
                     help="Track S follow-up generator")
    tui.add_argument("--workers", type=int, default=1,
                     help="concurrent provider arms (one thread per harness; each provider's cells "
                          "stay serial, different providers overlap). 1 = strictly serial (default)")
    tui.add_argument("--load", default="",
                     help="open a saved run (run dir or runrecord.json) in the IDE viewer instead of running")
    tui.set_defaults(func=cmd_tui)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (JudgeUnavailable, EmbeddingUnavailable) as exc:
        # a requested judge/embedding backend is unavailable — fail clean (we never silently downgrade)
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
