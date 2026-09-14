"""Aggregate all run results into a public static site (landing index + per-run reports).

Scans results/*/runrecord.json, rebuilds each report into site/public/runs/<run-id>/ with its
assets, and writes a branded landing page grouping runs by track with headline metrics. The
output (`benchmark/site/public/`) is what the deployed public site serves.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path

from .models import SCHEMA_VERSION, SCORING_VERSION
from .paths import RESULTS, ROOT
from .redaction import public_record
from .report import build_report
from .report_common import (
    COMMON_JS, COMPARISON_CSS, COMPARISON_JS, REPORT_CSS, REPORT_HEAD, navbar,
)
from .results_package import build_package, package_csv, render_package, sources, utility_evidence
from .site_visuals import category_path, render_category, render_overview

SITE = ROOT / "site"
DIST = SITE / "public"
PACKAGE_FILE = SITE / "results-package.json"

_TRACK = {
    "security": ("Security & Safety", "#e5484d", "Sentinel"),
    "quality": ("Code Quality & Output Security", "#6d5efb", "Auditor"),
    "generative": ("Generative Capability", "#16a34a", "Forge"),
    "project": ("Full-Repo Project Build", "#d97757", "Atelier"),
    "repo": ("Bugfix · Issue Resolution (SWE-bench-style)", "#0ea5e9", "Cobbler"),
}
# Category pages retain the original plots and explorers; Results owns the full tables.
_NAV_LABEL = {"security": "Security", "quality": "Quality", "generative": "Generative",
              "project": "Project", "repo": "Bugfix"}



def _nav_links(tracks: set[str], prefix: str) -> dict[str, str]:
    """Resolve root pages from either a site page or a canonical run report."""
    root = "" if prefix == "runs/" else "../../"
    links = {"Overview": f"{root}index.html"}
    links.update({_NAV_LABEL[t]: f"{root}{category_path(t)}" for t in _NAV_LABEL if t in tracks})
    links["Results"] = f"{root}results.html"
    links["Paper"] = f"{root}docs.html"
    return links


# Per-track headline metric: (per_harness path, lower_is_better, short noun, summary verb).
_METRIC = {
    "security": (("asr", "rate"), True, "successful jailbreak attacks", "blocks"),
    "quality": (("requirement_coverage",), False, "requirement coverage", "lifts"),
    "generative": (("g_score",), False, "generative capability score", "lifts"),
    "project": (("composite",), False, "full-repo build composite", "lifts"),
    "repo": (("composite",), False, "patch-quality composite", "lifts"),
}

# Cross-track Gauntlet Index: each track's per-harness headline normalized to 0-1 (higher = better;
# security is inverted from attack-success). The Overall index is the equal-weight mean over the
# tracks a harness has a score in.
_INDEX_METRIC = {
    "security": (("asr", "rate"), True),
    "quality": (("requirement_coverage",), False),
    "generative": (("g_score",), False),
    "project": (("composite",), False),
    "repo": (("composite",), False),
}
_INDEX_TRACKS = ("security", "quality", "generative", "project", "repo")
# Which Cortex preset wraps which base model, for the "Claude side vs Codex side" grouping.
_BASE_GROUP = {
    "codex_cli_raw": ("Codex", "base"), "cortex_wrapped": ("Codex", "cortex"),
    "omp": ("OMP", "base"), "cortex_omp": ("OMP", "cortex"),
    "claude_code": ("Claude", "base"), "cortex_claude": ("Claude", "cortex"),
    "opencode": ("OpenCode", "base"),
}


def _qualification_failures(record: dict) -> list[str]:
    """Reasons a run cannot supply public competitive headlines."""

    failures = []
    if record.get("schema_version") != SCHEMA_VERSION:
        failures.append("obsolete schema")
    if record.get("scoring_version") != SCORING_VERSION:
        failures.append("obsolete scoring")
    if not record.get("config", {}).get("live"):
        failures.append("synthetic or replayed run")
    config = record.get("config", {})
    if config.get("provider") == "rescored" or config.get("rescored_from"):
        failures.append("rescored historical observations")
    if record.get("config", {}).get("degraded"):
        failures.append("degraded configuration")
    if record.get("skipped"):
        failures.append("skipped cells")
    if not record.get("cases") or not record.get("results") or not record.get("harnesses"):
        failures.append("missing execution coverage")
    else:
        expected = {(case.get("id"), harness.get("id"))
                    for case in record["cases"] for harness in record["harnesses"]}
        actual = [(result.get("case_id", result.get("task_id", result.get("brief_id"))),
                   result.get("harness_id")) for result in record["results"]]
        if set(actual) != expected or len(actual) != len(expected):
            failures.append("incomplete or duplicate execution cells")
    if record.get("track") == "security":
        failures.append("live security containment is not attested")
    if any(result.get("error") or result.get("gen_error") for result in record.get("results", [])):
        failures.append("result errors")
    if record.get("track") == "generative":
        per_harness = record.get("aggregates", {}).get("per_harness", {})
        if not per_harness or any(metrics.get("evaluable") is not True for metrics in per_harness.values()):
            failures.append("unevaluable generative signals")
    if record.get("track") == "project":
        results = record.get("results", [])
        if not results or any(result.get("sandbox_backend") != "docker" for result in results):
            failures.append("unsealed project execution")
        if any(result.get("signals", {}).get("detail", {}).get("degraded") for result in results):
            failures.append("degraded project signals")
    return failures


def _eligible(record: dict) -> bool:
    return not _qualification_failures(record)


def _dig(node: dict, path: tuple[str, ...]):
    for key in path:
        node = (node or {}).get(key, {})
    return node if isinstance(node, int | float) else None


def _rel(raw: float | None, cortex: float | None, lower_is_better: bool) -> float | None:
    """Relative % change Cortex makes vs the raw base (the framing the colleague asked for)."""
    if raw is None or cortex is None or raw == 0:
        return None
    return ((raw - cortex) / raw) if lower_is_better else ((cortex - raw) / raw)


def _track_delta(rec: dict) -> dict:
    """raw-id / cortex-id + raw/cortex metric values + relative gain for a track's headline metric."""
    track = rec["track"]
    agg = rec["aggregates"]
    d = agg.get("harness_delta") or agg.get("synapse_delta") or {}
    ph = agg.get("per_harness", {})
    path, lower, noun, verb = _METRIC.get(track, ((), False, "", ""))
    raw_id, cortex_id = d.get("raw"), d.get("cortex_wrapped") or d.get("synapse")
    raw_v = _dig(ph.get(raw_id, {}), path) if raw_id else None
    cortex_v = _dig(ph.get(cortex_id, {}), path) if cortex_id else None
    if track == "security":
        if not (_dig(ph.get(raw_id, {}), ("asr", "n")) or 0) > 0:
            raw_v = None
        if not (_dig(ph.get(cortex_id, {}), ("asr", "n")) or 0) > 0:
            cortex_v = None
    return {"raw_id": raw_id, "cortex_id": cortex_id, "raw": raw_v, "cortex": cortex_v,
            "rel": _rel(raw_v, cortex_v, lower), "lower_is_better": lower, "noun": noun, "verb": verb}


_MEANINGFUL = 0.02  # relative gains below this are reported as parity, not a weak "+0%"


def _headline(rec: dict) -> str:
    if not _eligible(rec):
        return "non-qualifying run — " + ", ".join(_qualification_failures(rec))
    td = _track_delta(rec)
    if td["rel"] is None:
        return "qualified run — no paired headline"
    if abs(td["rel"]) < _MEANINGFUL:
        return f"head-to-head on {td['noun']} (parity on these tasks)"
    if td["rel"] < 0:  # cortex regressed on this metric — never dress a regression up as a win
        return f"raw harness leads on {td['noun']} by {abs(td['rel']) * 100:.0f}% on these tasks"
    return f"Cortex {td['verb']} {td['noun']} by {abs(td['rel']) * 100:.0f}% vs the raw harness"



def _meta(rec: dict, run_id: str) -> dict:
    name, color, codename = _TRACK.get(rec["track"], (rec["track"], "#5b6472", ""))
    return {
        "run_id": run_id, "track": rec["track"], "track_name": name, "color": color,
        "codename": codename, "created_at": rec.get("created_at", ""),
        "harnesses": len(rec.get("harnesses", [])), "cases": len(rec.get("cases", [])),
        "headline": _headline(rec),
        "qualified": _eligible(rec),
        "qualification_failures": _qualification_failures(rec),
    }


def _label_map(rec: dict) -> dict[str, str]:
    return {h["id"]: h.get("label", h["id"]) for h in rec.get("harnesses", [])}


def _asr_groups(rec: dict) -> list[dict]:
    """Jailbreak ASR per base model (lower = safer): paired first-party arms plus OpenCode ref."""
    ph = rec["aggregates"].get("per_harness", {})
    labels = _label_map(rec)
    groups: dict[str, dict] = {}
    for hid, (group, kind) in _BASE_GROUP.items():
        rate = _dig(ph.get(hid, {}), ("asr", "rate"))
        if rate is None or not (_dig(ph.get(hid, {}), ("asr", "n")) or 0) > 0:
            continue
        g = groups.setdefault(group, {"group": group, "base": None, "cortex": None,
                                      "base_label": "", "cortex_label": ""})
        g[kind] = round(rate, 4)
        g[f"{kind}_label"] = labels.get(hid, hid)
    order = ["Codex", "OMP", "Claude", "OpenCode"]
    return [groups[g] for g in order if g in groups]


def _gauntlet_index(records_by_id: dict[str, dict], latest_by_track: dict[str, str]) -> dict:
    """Per-harness, cross-track 'Gauntlet Index': each track normalized to 0-1 (higher = better), then
    an equal-weight mean = the Overall. The single comparable, competitive number per harness."""
    from .run import PRESETS

    scores: dict[str, dict[str, float]] = {}
    for track in _INDEX_TRACKS:
        rid = latest_by_track.get(track)
        if not rid:
            continue
        record = records_by_id[rid]
        if not _eligible(record):
            continue
        ph = record["aggregates"].get("per_harness", {})
        path, lower = _INDEX_METRIC[track]
        for hid, m in ph.items():
            v = _dig(m, path)
            if v is None or (track == "security" and not (_dig(m, ("asr", "n")) or 0) > 0):
                continue
            norm = (1.0 - v) if lower else v
            scores.setdefault(hid, {})[track] = round(max(0.0, min(1.0, norm)), 4)
    rows: list[dict] = []
    for hid, sc in scores.items():
        preset = PRESETS.get(hid)
        rows.append({
            "id": hid, "label": preset.label if preset else hid,
            "cortex": bool(getattr(preset, "uses_synapse", False)),
            "family": getattr(preset, "family", ""), "scores": sc,
            "overall": round(sum(sc.values()) / len(_INDEX_TRACKS), 4)
            if len(sc) == len(_INDEX_TRACKS) else None, "n_tracks": len(sc)})
    rows.sort(key=lambda r: (r["overall"] is not None, r["overall"] or 0.0), reverse=True)
    tracks = [t for t in _INDEX_TRACKS if any(t in r["scores"] for r in rows)]
    return {"tracks": tracks, "harnesses": rows}


def _summary(records_by_id: dict[str, dict], latest_by_track: dict[str, str]) -> dict:
    """Top-level 'pop' summary: the jailbreak hero chart + per-track relative-gain stat cards."""
    stats: list[dict] = []
    lead: dict | None = None
    asr_groups: list[dict] = []
    for track in ("security", "quality", "generative", "project", "repo"):
        rid = latest_by_track.get(track)
        if not rid:
            continue
        rec = records_by_id[rid]
        if not _eligible(rec):
            continue
        td = _track_delta(rec)
        name, color, codename = _TRACK[track]
        if td["rel"] is not None and abs(td["rel"]) >= _MEANINGFUL:  # don't lead with a parity result
            # sign reflects the METRIC's actual direction (did the value go down or up); `good` reflects
            # whether that is an improvement (rel>0). A regression must show its true sign and red, never
            # a fake "+" win.
            metric_down = td["cortex"] is not None and td["raw"] is not None and td["cortex"] < td["raw"]
            stats.append({
                "track": track, "name": name, "color": color, "codename": codename,
                "value": f"{'−' if metric_down else '+'}{abs(td['rel']) * 100:.0f}%", "noun": td["noun"],
                "good": td["rel"] >= 0, "href": f"runs/{rid}/report.html",
                "raw": td["raw"], "cortex": td["cortex"],
            })
        if track == "security":
            asr_groups = _asr_groups(rec)
            if td["rel"] is not None:
                lead = {"rel": round(td["rel"] * 100), "raw": td["raw"], "cortex": td["cortex"],
                        "href": f"runs/{rid}/report.html"}
    # average relative reduction across base-model pairs that have a Cortex variant (honest aggregate).
    # cortex == 0.0 (a full jailbreak elimination, the best outcome) must contribute rel = 1.0 — only
    # unpaired arms (cortex None) and base == 0 (relative change undefined) are excluded.
    pair_rels = [(g["base"] - g["cortex"]) / g["base"]
                 for g in asr_groups if g.get("base") not in (None, 0) and g.get("cortex") is not None]
    avg_rel = round(sum(pair_rels) / len(pair_rels) * 100) if pair_rels else (lead or {}).get("rel")
    index = _gauntlet_index(records_by_id, latest_by_track)
    return {"lead": lead, "avg_rel": avg_rel, "stats": stats, "asr_groups": asr_groups, "index": index}


def _build_paper(out_path: Path, links: dict) -> str:
    """Navigation-only rebuilds retain the unchanged paper's original generation date."""
    from .docs import build_docs

    previous = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
    html = build_docs(out_path, links)
    timestamp = re.compile(r"(?<=generated )\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?=\.</footer>)")
    old_stamp = timestamp.search(previous)
    if old_stamp:
        nav = re.compile(r"<nav\b[^>]*>.*?</nav>", re.DOTALL)
        before = timestamp.sub("", nav.sub("", previous, count=1))
        after = timestamp.sub("", nav.sub("", html, count=1))
        if before == after:
            html = timestamp.sub(old_stamp[0], html, count=1)
            out_path.write_text(html, encoding="utf-8")
    return html


def build_site() -> Path:
    records = []
    raw_hashes = {}
    for path in sorted(RESULTS.glob("*/runrecord.json")):
        raw_bytes = path.read_bytes()
        try:
            record = json.loads(raw_bytes)
        except json.JSONDecodeError:
            # An unreadable source cannot vouch for its cached public capture.
            # Revoke only that report, not unrelated, already-screened archives.
            cached = DIST / "runs" / path.parent.name
            if not cached.parent.is_symlink():
                if cached.is_symlink():
                    cached.unlink()
                elif cached.is_dir():
                    shutil.rmtree(cached)
            raise
        raw_hashes[path.parent.name] = hashlib.sha256(raw_bytes).hexdigest()
        published = public_record(record)
        if record["track"] == "security":
            published = {**published, "publication": {
                **published.get("publication", {}), "utility": utility_evidence(record),
            }}
        records.append((path.parent.name, record, published, path))
    # Recency applies only to qualified comparisons, never to the historical package.
    def _recency(run_id: str, record: dict) -> tuple[str, str]:
        ts = "-".join(run_id.split("-")[-3:])  # the YYYYMMDD-HHMMSS-mmm tail, prefix-independent
        return (record.get("created_at", ""), ts)

    qualified_by_track: dict[str, str] = {}
    qualified_best: dict[str, tuple[str, str]] = {}
    for run_id, record, _, _ in records:
        track = record["track"]
        key = _recency(run_id, record)
        if _eligible(record) and key >= qualified_best.get(track, ("", "")):
            qualified_best[track] = key
            qualified_by_track[track] = run_id
    records_by_id = {run_id: record for run_id, record, _, _ in records}
    published_by_id = {run_id: published for run_id, _, published, _ in records}
    package = build_package(json.loads(PACKAGE_FILE.read_text()), published_by_id, raw_hashes)
    package_tracks: set[str] = set()
    membership: dict[str, list[str]] = {}
    for collection, source, _ in sources(package):
        package_tracks.add(source["track"])
        if source["track"] == "security":
            source["asr_groups"] = _asr_groups(published_by_id[source["run_id"]])
        membership.setdefault(source["run_id"], []).append(collection["title"])

    # Resolve all historical inputs before touching the existing published snapshot.
    from .docs import _paper_downloads

    _paper_downloads(DIST / "docs.html")
    DIST.mkdir(parents=True, exist_ok=True)
    runs_dir = DIST / "runs"
    if runs_dir.exists():
        shutil.rmtree(runs_dir)
    runs_dir.mkdir(parents=True)

    selected_runs = {t["primary"]["run_id"] for c in package["collections"] for t in c["tracks"]}
    report_html_by_id = {}
    metas: list[dict] = []
    for run_id, record, published, record_path in records:
        # public_record may share the unflagged input; annotate a shallow copy only.
        published = {**published, "publication": {
            **published.get("publication", {}),
            "package": {"collections": membership.get(run_id, []),
                        "track_overview": f'../../{category_path(record["track"])}'
                        if record["track"] in package_tracks else None},
        }}
        # Preserve the model/harness labels recorded at execution time.
        dest = runs_dir / run_id
        dest.mkdir(parents=True)
        if not published.get("publication", {}).get("evidence_redacted"):
            for extra in ("assets", "screenshots"):
                src = record_path.parent / extra
                if src.exists():
                    shutil.copytree(src, dest / extra)
        # Cached historical HTML and media from restricted captures are not publication inputs.
        report_html = build_report(published, dest / "report.html", links=_nav_links(package_tracks, "../"))
        if run_id in selected_runs:
            report_html_by_id[run_id] = report_html
        metas.append(_meta(record, run_id))

    summary = _summary(records_by_id, qualified_by_track)
    summary["redacted_runs"] = sum(bool(published.get("publication", {}).get("evidence_redacted"))
                                   for _, _, published, _ in records)
    summary["package"] = package
    site_links = _nav_links(package_tracks, "runs/")
    from .report_common import LOGO_SVG
    (DIST / "favicon.svg").write_text(LOGO_SVG, encoding="utf-8")  # standalone asset for the deploy
    (DIST / "logo.svg").write_text(LOGO_SVG, encoding="utf-8")
    _build_paper(DIST / "docs.html", site_links)
    default_collection = min(package["collections"], key=lambda c: c["id"] != "reference")["id"]
    for collection in package["collections"]:
        for track in collection["tracks"]:
            source = track["primary"]
            category = render_category(
                report_html_by_id[source["run_id"]], published_by_id[source["run_id"]],
                source, collection, package,
                [meta for meta in metas if meta["track"] == source["track"]], _TRACK,
            )
            (DIST / category_path(source["track"], collection["id"], default=default_collection)).write_text(category, encoding="utf-8")
    (DIST / "results.html").write_text(_render_index(metas, summary, site_links), encoding="utf-8")
    (DIST / "index.html").write_text(
        render_overview(package, metas, _TRACK, site_links, published_by_id), encoding="utf-8"
    )
    (DIST / "results-package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    (DIST / "results-package.csv").write_text(package_csv(package), encoding="utf-8")
    return DIST


def _card(m: dict) -> str:
    return (
        f'<a class="run" href="runs/{escape(m["run_id"])}/report.html">'
        f'<div class="rt"><span class="dot" style="background:{m["color"]}"></span>'
        f'{escape(m["track_name"])} <span class="cn">{escape(m["codename"])}</span></div>'
        f'<div class="hl">{escape(m["headline"])}</div>'
        f'<div class="mt">{escape(m["run_id"])} · {m["harnesses"]} harnesses · {m["cases"]} cases · '
        f'{escape(m["created_at"])} · {"QUALIFIED" if m["qualified"] else "NON-COMPETITIVE"}</div></a>'
    )


# What each track measures — shown as the summary's "What we measure" appendix and mirrored in the
# generated docs template (agent-harness/benchmark-experiments.md).
_DOCS = {
    "security": ("Security &amp; Safety — jailbreak resistance",
        "Classifies captured responses and proposed actions across attack-delivery surfaces. "
        "ASR and benign over-refusal are conditional on observed cells. Regex replay is not "
        "authenticated side-effect evidence, and the live adapter does not enforce an outer "
        "agent sandbox. Do not interpret historical safety summaries as containment certification."),
    "quality": ("Code Quality &amp; Output Security",
        "Harnesses solve real coding tasks; we run real static analysis (Bandit / Semgrep, CWE-mapped), "
        "dependency checks, and the hidden acceptance tests (pytest), plus an LLM judge for "
        "architecture / readability. Reports requirement coverage, functional pass rate, vulnerabilities "
        "and maintainability."),
    "generative": ("Generative Capability",
        "Builds chat applications with a deterministic local endpoint stub, then evaluates "
        "feature probes, static code signals and optional visual evidence. The endpoint is not "
        "a learned model; historical echo checks do not prove endpoint use. Live trajectory and "
        "claim-evidence honesty are unobserved, so the full capability composite is unavailable."),
    "project": ("Full-Repo Project Build — Atelier",
        "One open-ended brief to build a whole storefront (backend + React/Vite frontend + PWA + cart + "
        "partial checkout probes) in a Docker evaluator; scored on a build-gated composite of "
        "functional checks, VERTEX similarity, static security, visual fidelity and architecture. "
        "Payment processing and complete accessibility are not established by these proxies."),
    "repo": ("Bugfix &amp; Issue Resolution — Cobbler",
        "Applies patches to repository issues and records visible, held-out and regression tests, "
        "strict resolution, patch quality and exploit flags. Historical results remain available "
        "with their original execution mode and scoring limitations."),
}


def _stat(s: dict) -> str:
    return (
        f'<a class="stat" href="{escape(s["href"])}">'
        '<div class="hint">Relative change</div>'
        f'<div class="{"sv" if s.get("good", True) else "sv bad"}">{escape(s["value"])}</div>'
        f'<div class="sn">{escape(s["noun"])}</div>'
        f'<div class="comparison-cue" data-direction="{"lower" if _METRIC[s["track"]][1] else "higher"}">'
        f'<span class="direction-pill">{"↓ Lower" if _METRIC[s["track"]][1] else "↑ Higher"} is better</span>'
        f'<span class="hint">Raw {s["raw"] * 100:.1f}% → '
        f'Cortex {s["cortex"] * 100:.1f}%</span></div>'
        f'<div class="sk"><span class="dot" style="background:{s["color"]}"></span>'
        f'{escape(s["name"])} <span class="go">view detail →</span></div></a>'
    )


def _docs_html() -> str:
    items = "".join(
        f'<div class="doc"><h3><span class="dot" style="background:{_TRACK[t][1]}"></span>{title}</h3>'
        f'<p>{body}</p></div>'
        for t, (title, body) in _DOCS.items()
    )
    return f'<div class="docs">{items}</div>'


def _render_index(metas: list[dict], summary: dict, links: dict[str, str] | None = None) -> str:
    by_track: dict[str, list[dict]] = {}
    for m in metas:
        by_track.setdefault(m["track"], []).append(m)
    cards = ""
    for track in _TRACK:
        runs = by_track.get(track, [])
        if not runs:
            continue
        rows = "".join(_card(m) for m in sorted(runs, key=lambda x: x["run_id"], reverse=True))
        cards += (f'<section class="track-results" id="track-{track}">'
                  f'<h3>{escape(_TRACK[track][0])} · {len(runs)} runs</h3>'
                  f'<div class="runs">{rows}</div></section>')

    stats = "".join(_stat(s) for s in summary.get("stats", []))
    avg_rel = summary.get("avg_rel")
    headline = (f"Recorded classified jailbreak reduction: ~{avg_rel}%"
                if avg_rel is not None else "No qualified comparison is currently available")
    generated = datetime.now().isoformat(timespec="seconds")
    return (
        _INDEX.replace("__HEAD__", REPORT_HEAD).replace("__CSS__", REPORT_CSS + COMPARISON_CSS)
        .replace("__NAVBAR__", navbar("", "Results", links))
        .replace("__COMMON_JS__", COMMON_JS + COMPARISON_JS)
        .replace("__HEADLINE__", escape(headline)).replace("__STATS__", stats)
        .replace("__CARDS__", cards).replace("__DOCS__", _docs_html())
        .replace("__PACKAGE__", render_package(summary["package"], _TRACK))
        .replace("__SUMMARY_JSON__", json.dumps(summary).replace("</", "<\\/"))
        .replace("__GENERATED__", generated).replace("__N__", str(len(metas)))
        .replace("__REDACTED__", str(summary.get("redacted_runs", 0)))
    )


_INDEX = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Gauntlet — historical benchmark results</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
__HEAD__
<style>__CSS__
  .pophero{display:flex;flex-direction:column;gap:6px;margin:8px 0 6px}
  .pophero h1{font-size:34px;line-height:1.15;letter-spacing:-.6px;margin:0;max-width:880px}
  .pophero .accent{color:var(--accent)}
  .lead{color:var(--muted);font-size:16px;max-width:820px;margin:6px 0 0}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:22px 0}
  a.stat{display:block;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
         background:var(--card);transition:border-color .15s,transform .15s}
  a.stat:hover{border-color:var(--accent);transform:translateY(-2px)}
  .stat .hint{color:var(--muted);font-size:12px}
  .sv{font-size:34px;font-weight:800;letter-spacing:-.5px;color:var(--metric-good)}
  .sv.bad{color:var(--metric-risk)}
  .sn{font-size:13px;color:var(--ink);margin-top:2px}
  .sk{font-size:12px;color:var(--muted);margin-top:10px;display:flex;align-items:center}
  .sk .go{margin-left:auto;color:var(--accent);font-weight:600}
  .dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px}
  .runs{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:8px}
  a.run{display:block;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-radius:14px;
        padding:16px 18px;background:var(--card);transition:border-color .15s,transform .15s}
  a.run:hover{border-color:var(--accent);transform:translateY(-2px)}
  .rt{font-weight:600;font-size:14px;display:flex;align-items:center;gap:2px}
  .cn{color:var(--muted);font-weight:400;margin-left:6px;font-size:12px}
  .hl{margin:8px 0 6px;font-size:15px;color:var(--accent)}
  .mt{color:var(--muted);font-size:12px}
  .track-results{scroll-margin-top:90px;margin-top:24px}
  #results{scroll-margin-top:90px}
  #package,.package-track{scroll-margin-top:90px}
  #package a{color:var(--accent)}
  .package-collection{margin-top:28px;border-top:1px solid var(--line);padding-top:18px}
  .package-track{margin:24px 0}
  .package-source p{overflow-wrap:anywhere}
  .package-table{overflow-x:auto}
  .package-table td,.package-table th{min-width:130px}
  .package-table small{color:var(--muted)}
  #indexTable{overflow-x:auto}
  #indexTable table{min-width:680px;table-layout:auto}
  #indexTable th,#indexTable td{word-break:normal;overflow-wrap:normal;white-space:nowrap}
  .package-alternative{margin-top:14px}
  .package-alternative summary{cursor:pointer;color:var(--accent);overflow-wrap:anywhere}
  .chart{height:340px;width:100%}
  .docs{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px}
  @media(max-width:820px){.docs{grid-template-columns:1fr}}
  .doc h3{font-size:14px;margin:0 0 4px;display:flex;align-items:center}
  .doc p{margin:0;color:var(--muted);font-size:13px;line-height:1.6}
</style></head><body>
__NAVBAR__
<div class="wrap">
  <header class="pophero">
    <h1>Complete historical benchmark results.</h1>
    <div style="font-size:20px;font-weight:700;margin-top:8px">Full reference matrices and captured histories, not the latest diagnostic sample.</div>
    <p class="lead">Cortex is a governance layer — hooks, policies, validation, long-horizon planning —
    that configures coding agents (Codex, OMP, Claude Code, OpenCode). The named collections below
    preserve recorded values, model identities and scoring provenance across all five tracks.
    Modeled references and captured/replayed outputs remain separate; there is no pooled overall score.</p>
    <p class="lead"><a href="#results">Browse all __N__ recorded benchmark runs across five tracks.</a></p>
    <p class="hint">The exhaustive package tables preserve source order, not rank. Column arrows show metric direction; provider identity is not a performance award.</p>
  </header>
  __PACKAGE__

  <section class="block" id="results">
    <h2><span class="chip" style="background:#6d5efb"></span>All benchmark results</h2>
    <div class="hint">Every recorded run is available below, including historical and noncompetitive
    results. __REDACTED__ reports have restricted evidence views: recorded measurements are retained,
    while captured text, generated files and media are withheld for publication safety.</div>
    __CARDS__
  </section>

  <div class="stats">__STATS__</div>
  <p class="hint">Current-scoring qualification: __HEADLINE__. Historical package values above
  are descriptive records, not qualified competitive claims.</p>

  <section class="block" id="indexBlock">
    <h2><span class="chip" style="background:#6d5efb"></span>Gauntlet Index — qualified five-family coverage</h2>
    <div class="hint">Every track is normalized to 0–100 (Security = 1−attack-success).
    Overall requires qualified scores on all five families; otherwise it is unavailable.
    Partial family scores remain visible. Matching coverage alone does not establish matched
    models, tasks, budgets, or a causal governance effect.</div>
    <div id="indexTable" style="overflow-x:auto"></div>
  </section>

  <section class="block">
    <h2><span class="chip" style="background:#e5484d"></span>Jailbreak attack-success — base harness vs Cortex</h2>
    <div class="hint">Lower classified attack-success is preferred. Only qualified observed
    comparisons appear here; historical summaries remain in the individual reports.</div>
    <div class="chart" id="hero_chart"></div>
  </section>


  <section class="block">
    <h2><span class="chip" style="background:#0aa5a5"></span>What we measure</h2>
    <div class="hint">Each report states its execution mode and measurement limits; synthetic examples are not experiments.</div>
    __DOCS__
  </section>

  <footer>__N__ runs · generated __GENERATED__ · interactive reports use Apache ECharts ·
  raw/governed labels identify configured arms, not proof of a controlled comparison.
  Reproduce: <code>python -m gauntlet run --track {security|quality|generative|project|repo}</code>.</footer>
</div>
<script id="summary" type="application/json">__SUMMARY_JSON__</script>
<script>__COMMON_JS__</script>
<script>
const S = JSON.parse(document.getElementById('summary').textContent);
function renderHero(){
  const dom=document.getElementById('hero_chart');if(!dom)return;
  const groups=S.asr_groups||[],chart=echarts.getInstanceByDom(dom)||echarts.init(dom);
  comparisonCue('hero_chart','lower',groups.length?'Lower attack success first within each base-model group.':'No qualified observed comparisons.',
    'Green marks the leading observed value within a pair, not Cortex by default. An unpaired arm does not establish a winner.');
  if(!groups.length){chart.setOption({graphic:{type:'text',left:'center',top:'middle',
    style:{text:'No qualified observed comparisons',fill:harnessInk(),fontSize:14}},series:[]},true);return;}
  const compact=dom.clientWidth<480;
  const rows=groups.flatMap(g=>{
    const comparison=metricComparison(['base','cortex'].filter(role=>g[role+'_label']||g[role]!=null).map(role=>({role,value:g[role],label:g[role+'_label']||(role==='base'?'Base harness':'With Cortex')})),r=>r.value,'lower');
    return comparison.rows.map(row=>({label:g.group+' · '+row.label+(row.value==null?' · unavailable':''),value:row.value,color:comparisonColor(comparison,row)}));});
  chart.setOption({
    grid:{left:compact?145:190,right:55,top:12,bottom:36},
    tooltip:{trigger:'axis',valueFormatter:v=>v==null?'unavailable':(v*100).toFixed(1)+'%'},
    xAxis:{type:'value',min:0,max:1,splitNumber:compact?2:5,axisLabel:{formatter:v=>(v*100)+'%',color:axisInk(),hideOverlap:true},splitLine:{lineStyle:{type:'dashed',color:gridInk()}}},
    yAxis:{type:'category',inverse:true,data:rows.map(r=>r.label),axisTick:{show:false},axisLine:{show:false},axisLabel:{color:harnessInk(),fontSize:11,width:compact?135:180,overflow:'truncate'}},
    series:[{type:'bar',barMaxWidth:24,data:rows.map(r=>({value:r.value,itemStyle:{color:r.color,borderRadius:[0,4,4,0]}})),
      label:{show:true,position:'right',formatter:p=>p.value==null?'':(p.value*100).toFixed(1)+'%',color:harnessInk(),fontWeight:600}}]
  },true);
}
function renderIndex(){
  const ix=S.index,el=document.getElementById('indexTable');if(!el)return;
  const comparison=metricComparison(ix?.harnesses||[],h=>h.overall),rows=comparison.rows;
  const fmt=v=>v==null?'unavailable':(v*100).toFixed(1);
  comparisonCue('indexTable','higher','Overall: '+comparisonSummary(comparison,h=>h.label,fmt),
    'Overall ranks require complete coverage. Family columns have separate leaders. On narrow screens, scroll the table horizontally to compare families.');
  if(!rows.length){el.textContent='No qualified rows are available.';return;}
  const tn={security:'Security',quality:'Quality',generative:'Generative',project:'Project',repo:'Bugfix'};
  const columns=ix.tracks.map(t=>({label:(tn[t]||t)+' ↑',value:h=>h.scores[t]}));
  columns.push({label:'Overall ↑',value:h=>h.overall});
  columns.forEach(col=>col.comparison=metricComparison(rows,col.value));
  const table=document.createElement('table');table.style.width='100%';table.style.borderCollapse='collapse';
  const head=table.createTHead().insertRow();
  ['Harness',...columns.map(c=>c.label)].forEach(text=>{const th=document.createElement('th');th.scope='col';th.textContent=text;head.append(th);});
  const body=table.createTBody();
  rows.forEach(h=>{const tr=body.insertRow();tr.insertCell().textContent=h.label;
    columns.forEach(col=>{const td=tr.insertCell();td.textContent=fmt(col.value(h));td.style.textAlign='center';
      if(col.comparison.leaders.includes(h)){td.style.fontWeight='800';td.style.color='var(--metric-good)';td.title=comparisonSummary(col.comparison,x=>x.label,fmt);}});
    if(h.n_tracks<5)tr.lastElementChild.append(' · '+h.n_tracks+'/5 families');
  });
  el.replaceChildren(table);
}
function renderResults(){renderIndex();renderHero();}
renderResults();window.__charts=renderResults;
window.addEventListener('resize',()=>{const d=document.getElementById('hero_chart');const c=d&&echarts.getInstanceByDom(d);if(c){c.resize();renderHero();}});
</script>
</body></html>
"""
