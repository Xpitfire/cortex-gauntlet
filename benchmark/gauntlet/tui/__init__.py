"""Gauntlet experiment TUI — a reusable, IDE-style live view for benchmark runs.

Layered so the display is decoupled from execution and reusable for any experiment:
- `events`: the typed event stream + bus (the contract between a runner and any observer).
- `model`: a framework-agnostic view-model (ExperimentTree) built from the event stream.
- `runner`: ExperimentRunner — runs cells with per-cell exception isolation, emitting events.
- `bridge`: turns each Gauntlet track (items × harnesses) into runnable cells + finalize.
- `console`: a non-TUI observer (CI / no-TTY fallback) — proves the core is reusable.
- `app`: the Textual IDE (tree + main view + terminal preview + progress) consuming the bus.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .events import CellRef, CellStatus, EventBus, Observer
from .model import Cell, ExperimentTree, Group
from .runner import CellOutcome, CellSpec, ExperimentRunner

__all__ = [
    "Cell",
    "CellOutcome",
    "CellRef",
    "CellSpec",
    "CellStatus",
    "EventBus",
    "ExperimentRunner",
    "ExperimentTree",
    "Group",
    "Observer",
    "run_suite_tui",
    "run_tui",
]


def run_tui(
    track: str = "security", *, live: bool = False, provider: str = "codex", seeds: int = 5,
    suite: str = "security", run_dir: Path | None = None, force_console: bool = False,
    only: tuple[str, ...] = (), limit: int = 0, load: str | Path | None = None,
    network_policy: str = "none", vision_judge: str = "heuristic", synapse_iterations: int = 3,
    judge: str = "auto", vertex_ref: str = "auto", security_passes: int = 1,
    red_team: str = "auto", workers: int = 1,
) -> None:
    """Launch the experiment IDE for a track, load a saved run for viewing, or print to the console."""

    if load is not None:  # viewer mode: open a saved runrecord.json (from any past run)
        from .bridge import load_run

        tree = load_run(Path(load))
        if force_console or not sys.stdout.isatty():
            from .events import CellStatus

            print(f"loaded {tree.track} run · {tree.done} cells · "
                  f"✓{tree.count(CellStatus.PASS)} ✗{tree.count(CellStatus.FAIL)} "
                  f"⚠{tree.count(CellStatus.ERROR)} –{tree.count(CellStatus.SKIP)}")
            return
        from .app import GauntletApp

        GauntletApp(tree.track, [], loaded=tree).run()
        return

    from .bridge import build_specs

    specs, finalize = build_specs(
        track, live=live, provider=provider, seeds=seeds, suite=suite, run_dir=run_dir,
        only=only, limit=limit, network_policy=network_policy, vision_judge=vision_judge,
        synapse_iterations=synapse_iterations, judge=judge, vertex_ref=vertex_ref,
        security_passes=security_passes, red_team=red_team,
    )
    # a checkpoint under the run dir makes the run resumable and lets it pause (not fail) on a rate limit
    checkpoint = None
    if run_dir is not None:
        from ..resilience import Checkpoint

        checkpoint = Checkpoint(Path(run_dir) / "checkpoint.jsonl")
    if force_console or not sys.stdout.isatty():
        from .console import ConsoleObserver

        bus = EventBus()
        bus.subscribe(ConsoleObserver())
        finished = ExperimentRunner(bus).run(track, specs, finalize, checkpoint=checkpoint,
                                             workers=workers)
        if finished.paused:
            print(f"\nPAUSED — rate limited ({finished.pause_reason}). "
                  f"resume with:  --resume {Path(run_dir).name}")
        return

    from .app import GauntletApp

    GauntletApp(track, specs, finalize, checkpoint=checkpoint, workers=workers).run()


_SUITE_TUI_TRACKS = ("security", "quality", "generative", "project", "repo")  # all have TUI cell builders


def run_suite_tui(
    tracks: list[str], *, live: bool = False, provider: str = "codex",
    seeds_for: dict[str, int] | None = None, network_policy: str = "none",
    vision_judge: str = "heuristic", synapse_iterations: int = 3, force_console: bool = False,
    judge: str = "auto", resume_dir=None, vertex_ref: str = "auto", security_passes: int = 1,
    red_team: str = "auto", workers: int = 1,
) -> None:
    """Run several tracks in ONE Textual app — a section per track — instead of a window per track.

    Each track's cells are built via `build_specs` (own run dir + finalize) and concatenated with
    track-prefixed group names so the tree sections by track; a combined finalize writes each track's
    runrecord."""

    import dataclasses

    from ..paths import RESULTS
    from ..resilience import Checkpoint
    from ..run import new_run_id
    from .bridge import build_specs

    seeds_for = seeds_for or {}
    all_specs: list = []
    finalizers: dict[str, object] = {}
    run_dirs: list[Path] = []  # per-track dirs — used to tear down kept-alive review containers on close
    for track in tracks:
        if track not in _SUITE_TUI_TRACKS:
            continue
        run_dir = RESULTS / f"tui-{new_run_id(track)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        run_dirs.append(run_dir)
        specs, finalize = build_specs(
            track, live=live, provider=provider, seeds=seeds_for.get(track, 1), run_dir=run_dir,
            network_policy=network_policy, vision_judge=vision_judge,
            synapse_iterations=synapse_iterations, judge=judge, vertex_ref=vertex_ref,
            security_passes=security_passes, red_team=red_team,
        )
        finalizers[track] = finalize
        for spec in specs:  # prefix the group with the track so the single tree sections by track
            ref = dataclasses.replace(spec.ref, group=f"{track} · {spec.ref.group}")
            all_specs.append(dataclasses.replace(spec, ref=ref))
    if not all_specs:
        return

    def finalize_all(pairs: list) -> str | None:
        last = None
        for track, finalize in finalizers.items():
            track_pairs = [p for p in pairs if p[0].ref.track == track]
            if track_pairs:
                last = finalize(track_pairs)
        return last

    # resume reuses the given dir's checkpoint (skip done cells); else a fresh suite dir
    suite_dir = Path(resume_dir) if resume_dir is not None else RESULTS / f"tui-suite-{new_run_id('suite')}"
    suite_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(suite_dir / "checkpoint.jsonl")
    print(f"  run id: {suite_dir.name}\n"
          f"  pause:  ctrl+z in the TUI, or `cortex benchmark pause {suite_dir.name}` from another "
          f"terminal (finishes the current cell, then stops — nothing fails)\n"
          f"  resume: cortex benchmark suite --resume {suite_dir.name} --live --provider <list>\n")
    def _teardown_review_containers() -> None:
        # kept-alive project review containers (GAUNTLET_KEEP_CONTAINERS=1) live only while the TUI is
        # open; remove them — and their ephemeral images — when it closes, plus a host-wide safety sweep.
        from ..project import containers

        kept = sum(len(containers.list_kept(rd)) for rd in run_dirs)
        if kept:
            print(f"  ▸ tearing down {kept} review container(s)…")
        for rd in run_dirs:
            containers.cleanup(rd)
        containers.cleanup_all()

    if force_console or not sys.stdout.isatty():
        from .console import ConsoleObserver

        bus = EventBus()
        bus.subscribe(ConsoleObserver())
        try:
            ExperimentRunner(bus).run("suite", all_specs, finalize_all, checkpoint=checkpoint,
                                      workers=workers)
        finally:
            _teardown_review_containers()
        return

    from .app import GauntletApp

    try:
        GauntletApp("suite", all_specs, finalize_all, checkpoint=checkpoint, workers=workers).run()
    finally:
        _teardown_review_containers()
