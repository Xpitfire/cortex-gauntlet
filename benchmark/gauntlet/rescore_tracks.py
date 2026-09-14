"""Re-score a finished run of ANY functional track from its PERSISTED artifacts — re-run the CURRENT
scoring on the already-generated code (+ the captured execution observation) WITHOUT re-invoking the
BUILD harness (no new code generation, the expensive part).

The SCORING backends are NOT skipped: whatever judge you configure runs in the loop — heuristic, the
local CLIP vision judge, or an LLM judge (`--judge claude`, `--vision-judge clip|claude-vision`).
Re-score only avoids regenerating the repo, not evaluating it.

- project: reconstruct each arm's Candidate from `sandbox/<h>/{repo, result.json}` (the persisted probe
  observation) and re-run `score_project` with the configured judges — no Docker rebuild.
- quality / repo: REPLAY the persisted generated code through the real per-task scorer (which re-runs
  the analyzers + hidden tests with the current scoring) via a no-regeneration `ReplayCodegen`.
- security lives in `gauntlet.rescore` (re-judge the captured response with the configured judge).
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

from .livegen.models import CodeGenResult
from .paths import RESULTS


class ReplayCodegen:
    """A codegen that REPLAYS persisted files instead of calling a model — so the real scorer re-runs
    on the captured code with no new generation (duck-types the CodeGenAdapter Protocol)."""

    def __init__(self, files: dict[str, str]):
        self._files = dict(files)

    def generate(self, request) -> CodeGenResult:  # noqa: ARG002 — the prompt is irrelevant on replay
        return CodeGenResult(backend="replay", main_code="", files=dict(self._files),
                             ok=bool(self._files), error="" if self._files else "no persisted files")


def _persisted_cells(run_dir: Path) -> dict[tuple[str, str], dict[str, str]]:
    """{(task_id, harness_id): generated files} from the run's persisted code — the checkpoint's captured
    cells when present (full code), else the runrecord results (headless tracks like repo have no
    checkpoint but persist their patch/code there)."""

    cells: dict[tuple[str, str], dict[str, str]] = {}
    ckpt = run_dir / "checkpoint.jsonl"
    if ckpt.exists():
        for line in ckpt.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            parts, outcome = rec.get("key", "").split("/"), rec.get("outcome", {})
            if len(parts) >= 2 and outcome.get("files"):
                cells[(parts[-2], parts[-1])] = {p: c for p, c in outcome["files"].items()
                                                 if not p.startswith("_")}
    if cells:
        return cells
    rr = run_dir / "runrecord.json"  # fallback: code persisted in the runrecord results
    if rr.exists():
        for r in json.loads(rr.read_text()).get("results", []):
            files, tid, hid = r.get("files") or {}, r.get("task_id") or r.get("brief_id"), r.get("harness_id")
            if files and tid and hid:
                cells[(tid, hid)] = {p: c for p, c in files.items() if not p.startswith("_")}
    return cells


def _raw(harness):
    """Treat a Synapse-wrapped harness as raw for replay: the persisted code is the FINAL repo, so one
    'generation' (the replay) re-scores it — we don't re-run the planning loop on replay."""

    return (dataclasses.replace(harness, uses_synapse=False)
            if getattr(harness, "uses_synapse", False) else harness)


def _used_tasks(tasks: dict, results) -> list:
    """The distinct tasks actually scored (QualityTask/RepoTask are unhashable, so key by id)."""

    return list({r.task_id: tasks[r.task_id] for r in results if r.task_id in tasks}.values())


# ---- project: reconstruct from the persisted sandbox observation (no Docker) -------------------------
def _project_candidate(brief, arm_dir: Path):
    from .bootstrap import app_files
    from .project.arch import architecture_descriptors
    from .project.models import Candidate
    from .project.sandbox import _capabilities

    repo_dir = arm_dir / "repo"
    files = {}
    for p in repo_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif"):
            try:
                files[str(p.relative_to(repo_dir))] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    res = json.loads((arm_dir / "result.json").read_text())
    ui = res.get("ui", {})
    shots = {s: str(arm_dir / f"{s}.png") for s in ("home", "listing", "pdp", "cart")
             if (arm_dir / f"{s}.png").exists()}
    return Candidate(
        harness_id=arm_dir.name, built=True, served=bool(res.get("served")), files=files,
        capabilities=_capabilities(brief.acceptance, res),
        journey_pass={j["id"]: bool(j.get("passed")) for j in ui.get("journeys", [])},
        journey_eval={j["id"]: bool(j.get("evaluable", True)) for j in ui.get("journeys", [])},
        pwa_a11y={c["id"]: bool(c.get("passed")) for c in res.get("pwa_a11y", ui.get("pwa_a11y", []))},
        robustness={c["id"]: bool(c.get("passed")) for c in res.get("robustness", [])},
        module_descriptors=architecture_descriptors(app_files(files)), screenshots=shots)


def rescore_project(run_dir: Path, *, vision_judge: str = "auto", vertex_ref: str = "auto", **_kw) -> dict:
    from .project.corpus import load_project_brief
    from .project.judge import build_project_judges
    from .project.run import build_project_record
    from .project.score import score_project
    from .project.vertexqe import resolve_ref_mode
    from .run import PRESETS, new_run_id

    source_path = run_dir / "runrecord.json"
    source = json.loads(source_path.read_text()) if source_path.exists() else {}
    brief = load_project_brief()
    judges = build_project_judges(vision_judge, live=True)  # honours the configured judge (clip/claude-vision)
    resolved_vertex_ref = resolve_ref_mode(vertex_ref, live=True)
    out = _target(run_dir, _kw)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    results, harnesses = [], []
    for arm in sorted((run_dir / "sandbox").glob("*")):
        if not (arm / "result.json").exists() or not (arm / "repo").is_dir():
            continue
        cand = _project_candidate(brief, arm)
        r = score_project(brief, cand, judges, sandbox_backend="docker", vertex_ref=resolved_vertex_ref)
        rewritten = {}  # copy the persisted renders into the new report's assets/
        for screen, path in cand.screenshots.items():
            png = Path(path)
            if png.exists():
                dst = f"{arm.name}-{png.name}"
                shutil.copy(png, assets / dst)
                rewritten[screen] = f"assets/{dst}"
        r.screenshots = rewritten
        results.append(r)
        if arm.name in PRESETS:
            harnesses.append(PRESETS[arm.name])
    # in-place correction preserves the original run identity; a copy gets a fresh -rescored id
    rid = None
    if _kw.get("in_place"):
        try:
            rid = json.loads((run_dir / "runrecord.json").read_text()).get("run_id")
        except (json.JSONDecodeError, OSError):
            rid = None
    record = build_project_record(brief, results, harnesses, run_id=rid or new_run_id("project-rescored"),
                                  live=bool(source.get("config", {}).get("live")), provider="rescored",
                                  judge_backend=judges.backend,
                                  vertex_ref=resolved_vertex_ref)
    record.config["rescored_from"] = run_dir.name
    return _emit(out, record, len(results))


# ---- quality / repo: replay the persisted code through the real scorer -------------------------------
def rescore_quality(run_dir: Path, **_kw) -> dict:
    from .quality.corpus import load_quality_tasks
    from .quality.judge import HeuristicQualityJudge
    from .quality.run import build_quality_record
    from .quality.score import score_task
    from .run import PRESETS, new_run_id
    from .synapse import SynapsePlanner

    tasks = {t.id: t for t in load_quality_tasks()}
    planner, judge = SynapsePlanner(), HeuristicQualityJudge()
    results, seen = [], {}
    for (case_id, hid), files in _persisted_cells(run_dir).items():
        task, meta = tasks.get(case_id), PRESETS.get(hid)
        if task and meta:
            results.append(score_task(task, _raw(meta), planner, judge, ReplayCodegen(files)))
            seen[hid] = meta
    config = {"suite": "quality", "judge": "rescored:heuristic", "seeds": 1, "rescored_from": run_dir.name}
    record = build_quality_record(_used_tasks(tasks, results), results, list(seen.values()),
                                  run_id=new_run_id("quality-rescored"), config=config, planner=planner)
    return _emit(_target(run_dir, _kw), record, len(results))


def rescore_repo(run_dir: Path, **_kw) -> dict:
    from .repo.corpus import load_repo_tasks
    from .repo.run import build_repo_record
    from .repo.score import score_repo_task
    from .run import PRESETS, new_run_id

    source_path = run_dir / "runrecord.json"
    source = json.loads(source_path.read_text()) if source_path.exists() else {}
    tasks = {t.id: t for t in load_repo_tasks()}
    results, seen = [], {}
    for (case_id, hid), files in _persisted_cells(run_dir).items():
        task, meta = tasks.get(case_id), PRESETS.get(hid)
        if task and meta:
            results.append(score_repo_task(task, _raw(meta), ReplayCodegen(files)))
            seen[hid] = meta
    record = build_repo_record(_used_tasks(tasks, results), results, list(seen.values()),
                               run_id=new_run_id("repo-rescored"),
                               live=bool(source.get("config", {}).get("live")), provider="rescored")
    record.config["rescored_from"] = run_dir.name
    return _emit(_target(run_dir, _kw), record, len(results))


# ---- generative: REUSE the execution observation, RECOMPUTE only the static signals -----------------
def _gen_result_from_dict(d: dict):
    """Reconstruct a GenerativeResult from its serialized form (nested FeatureOutcome list rebuilt)."""

    from .generative.models import FeatureOutcome, GenerativeResult

    fields = {f.name for f in dataclasses.fields(GenerativeResult)}
    kw = {k: v for k, v in d.items() if k in fields}
    kw["rep_features"] = [FeatureOutcome(**f) if isinstance(f, dict) else f
                          for f in d.get("rep_features", [])]
    return GenerativeResult(**kw)


def _app_brief_from_dict(d: dict):
    """Reconstruct an AppBrief (nested FeatureSpec list rebuilt) from a runrecord's persisted case."""

    from .enums import Language
    from .generative.models import AppBrief, FeatureSpec

    fields = {f.name for f in dataclasses.fields(AppBrief)}
    kw = {k: v for k, v in d.items() if k in fields}
    kw["language"] = Language(d.get("language", "python"))
    kw["features"] = [FeatureSpec(**f) if isinstance(f, dict) else f for f in d.get("features", [])]
    return AppBrief(**kw)


def rescore_generative(run_dir: Path, **_kw) -> dict:
    """Re-score the generative track WITHOUT re-running the sandbox (SLM sidecar + probe): the feature /
    build / visual / plan observation is reused from the persisted result; only the static-quality
    signals (ruff/eslint+tsc lint, Semgrep/Bandit security) are recomputed on the persisted app code —
    exactly the signals a scoring fix changes."""

    from .analysis import lint_type_metrics, scan_repo, security_score
    from .generative.corpus import load_briefs
    from .generative.run import build_generative_record
    from .run import PRESETS, new_run_id
    from .synapse import SynapsePlanner

    rr = run_dir / "runrecord.json"
    if not rr.exists():
        return {"rescored": 0, "error": "no runrecord.json to re-score from"}
    data = json.loads(rr.read_text())
    # rebuild the record against the ORIGINAL run's briefs (persisted in `cases`) — a live run's brief
    # ids (chat-app/notes-app/…) don't exist in the mock corpus, and a mock-corpus rebuild would emit
    # cases that match no result (broken report explorer, wrong feature_count).
    briefs = [_app_brief_from_dict(c) for c in data.get("cases", [])] or load_briefs()
    cells = _persisted_cells(run_dir)  # (brief_id, harness) -> app files (checkpoint preferred)
    results, seen = [], {}
    for d in data.get("results", []):
        files = cells.get((d.get("brief_id"), d.get("harness_id"))) or d.get("files") or {}
        if files:  # recompute the static signals on the persisted code; reuse them if no code is kept
            lt = lint_type_metrics(files, d.get("language", ""))
            findings, sec_tool = scan_repo(files)
            d = {**d, "lint_issues": lt.lint_issues, "type_errors": lt.type_errors,
                 "code_quality": round(0.5 * lt.lint_score + 0.5 * lt.type_score, 4),
                 "security": round(security_score(findings), 4), "findings": len(findings),
                 "security_tool": sec_tool}
        results.append(_gen_result_from_dict(d))
        if d.get("harness_id") in PRESETS:
            seen[d["harness_id"]] = PRESETS[d["harness_id"]]
    seeds = (data.get("config") or {}).get("seeds", 1)
    config = {"suite": "generative", "judge": "rescored", "seeds": seeds, "rescored_from": run_dir.name}
    record = build_generative_record(briefs, results, list(seen.values()),
                                     run_id=new_run_id("generative-rescored"), config=config,
                                     planner=SynapsePlanner(), seeds=seeds)
    return _emit(_target(run_dir, _kw), record, len(results))


def _target(run_dir: Path, kw: dict) -> Path:
    """Where the re-scored runrecord/report land: the ORIGINAL run dir when `in_place` (correct it so a
    reopened/resumed run shows the fixed numbers), else a non-destructive `<name>-rescored` copy."""
    return run_dir if kw.get("in_place") else run_dir.parent / f"{run_dir.name}-rescored"


def _emit(out: Path, record, n: int) -> dict:
    from .report import build_report

    out.mkdir(parents=True, exist_ok=True)
    (out / "runrecord.json").write_text(record.to_json(), encoding="utf-8")
    build_report(json.loads(record.to_json()), out / "report.html")
    return {"rescored": n, "out_dir": str(out),
            "paths": {"runrecord": str(out / "runrecord.json"), "report": str(out / "report.html")}}


_TRACK_RESCORERS = {"project": rescore_project, "quality": rescore_quality, "repo": rescore_repo,
                    "generative": rescore_generative}


def _detect_track(run_dir: Path) -> str | None:
    for t in ("project", "quality", "repo", "generative", "security"):
        if f"-{t}-" in run_dir.name or run_dir.name.startswith((f"tui-{t}-", f"{t}-")):
            return t
    rr = run_dir / "runrecord.json"
    if rr.exists():
        try:
            return json.loads(rr.read_text()).get("track")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _latest_run(track: str) -> Path | None:
    runs = sorted((d for d in RESULTS.glob(f"*{track}*")
                   if d.is_dir() and "rescored" not in d.name and "suite-suite" not in d.name),
                  key=lambda d: d.name, reverse=True)
    return runs[0] if runs else None


def rescore(*, run: str = "", tracks: tuple[str, ...] = (), judge: str = "heuristic",
            vision_judge: str = "auto", vertex_ref: str = "auto", in_place: bool = False) -> dict:
    """Re-score one run (`run`) or the latest run of each selected track (`tracks`, or all functional
    tracks). The configured `judge`/`vision_judge` are USED in the loop — re-score never skips them.
    `in_place=True` overwrites the ORIGINAL run's runrecord/report with the corrected numbers (so a
    reopened/resumed run shows them) instead of writing a non-destructive `<name>-rescored` copy."""

    jobs: list[tuple[str, Path]] = []
    if run:
        run_dir = Path(run) if "/" in run else RESULTS / run
        track = _detect_track(run_dir)
        if track:
            jobs.append((track, run_dir))
    else:
        for t in (tracks or ("project", "quality", "repo", "security")):
            rd = _latest_run(t)
            if rd:
                jobs.append((t, rd))
    out: dict[str, dict] = {}
    for track, run_dir in jobs:
        try:
            if track == "security":
                from .rescore import rescore_run
                out[track] = rescore_run(run_dir, judge_name=judge)  # in-place not wired for security
            elif track in _TRACK_RESCORERS:
                out[track] = _TRACK_RESCORERS[track](run_dir, judge=judge, vision_judge=vision_judge,
                                                     vertex_ref=vertex_ref, in_place=in_place)
            else:
                out[track] = {"error": f"re-score for '{track}' not yet wired (needs re-execution sidecars)",
                              "run": str(run_dir)}
        except Exception as exc:  # noqa: BLE001 — one track's failure must not abort the others
            out[track] = {"error": f"{type(exc).__name__}: {exc}", "run": str(run_dir)}
    return out
