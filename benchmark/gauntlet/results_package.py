"""Curated historical result collections, separate from competitive qualification."""

from __future__ import annotations

import csv
import io
import json
from html import escape

# Persisted measurements, not a new scoring formula. Missing values stay unavailable.
METRICS = {
    "security": (
        ("asr.rate", "Attack success ↓"),
        ("over_refusal.rate", "Over-refusal ↓"),
        ("secure_useful.rate", "Secure and useful ↑"),
    ),
    "quality": (
        ("checks.overall.rate", "Overall checks ↑"),
        ("requirement_coverage", "Coverage ↑"),
        ("functional_rate", "Functional success ↑"),
    ),
    "generative": (
        ("g_score", "Recorded capability ↑"),
        ("completeness", "Completeness ↑"),
        ("build_rate", "Build rate ↑"),
    ),
    "project": (
        ("composite", "Recorded composite ↑"),
        ("functional", "Functional success ↑"),
        ("vertex", "VERTEX ↑"),
    ),
    "repo": (
        ("composite", "Recorded composite ↑"),
        ("strict_rate", "Strict resolution ↑"),
        ("resolution_rate", "Resolution ↑"),
    ),
}


def _measurement(metrics: dict, path: str) -> float | int | None:
    value = metrics
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _provenance(record: dict) -> dict:
    judges, instruments = set(), set()
    for result in record.get("results", []):
        score = result.get("score", {})
        if not isinstance(score, dict):
            continue
        if judge := _text(score.get("judge_model")):
            judges.add(judge)
        if instrument := _text(score.get("instrument")):
            instruments.add(instrument)
    config = record.get("config", {})
    return {
        "declared_judge": _text(config.get("judge")),
        "declared_judge_model": _text(record.get("methodology", {}).get("judge_model")),
        "recorded_score_judges": sorted(judges),
        "recorded_score_instruments": sorted(instruments),
        "rescored_from": _text(config.get("rescored_from")),
    }

def utility_evidence(record: dict) -> dict[str, dict[str, str]]:
    """Qualify retained marker flags without rewriting historical measurements."""
    adapters = record.get("config", {}).get("adapters", [])
    declared = list(adapters.values()) if isinstance(adapters, dict) else adapters
    modeled_ids = {a.partition(":")[2] for a in declared
                   if isinstance(a, str) and a.startswith("mock:")}
    evidence = {}
    for harness in record.get("harnesses", []):
        metrics = record.get("aggregates", {}).get("per_harness", {}).get(harness["id"], {})
        utility = metrics.get("secure_useful") or metrics.get("utility_under_attack") or {}
        if utility.get("rate") is None or utility.get("n") == 0:
            status, note = "unavailable", "No utility observations; an empty denominator is not a zero success rate."
        elif harness["id"] in modeled_ids:
            status, note = "modeled", "Synthetic completion-marker result, not measured live task completion."
        else:
            status, note = "unverified", (
                "Historical marker result: absence of a synthetic marker was recorded as failure. "
                "Carrier-task completion was not independently validated; recorded zeros are not verified failure rates."
            )
        evidence[harness["id"]] = {"status": status, "note": note}
    return evidence



def build_package(manifest: dict, records: dict[str, dict], raw_hashes: dict[str, str]) -> dict:
    """Resolve explicit archive identities; never substitute a newer or better-scoring run."""

    def source(track: str, run_id: str) -> dict:
        if run_id not in records:
            raise ValueError(f"Historical package source is missing: {run_id}")
        record = records[run_id]
        if record["track"] != track:
            raise ValueError(f"Historical package track mismatch: {run_id} is not {track}")
        harnesses = record.get("harnesses", [])
        aggregates = record.get("aggregates", {}).get("per_harness", {})
        rows = [
            {
                "id": h["id"],
                "label": h.get("label", h["id"]),
                "model": h.get("model"),
                "values": {
                    path: _measurement(aggregates.get(h["id"], {}), path)
                    for path, _ in METRICS[track]
                },
            }
            for h in harnesses
        ]
        return {
            "run_id": run_id,
            "recorded_run_id": record.get("run_id"),
            "track": track,
            "source_sha256": raw_hashes[run_id],
            "href": f"runs/{run_id}/report.html",
            "created_at": record.get("created_at"),
            "provenance": _provenance(record),
            "schema_version": record.get("schema_version"),
            "scoring_version": record.get("scoring_version"),
            "cases": len(record.get("cases", [])),
            "harnesses": len(harnesses),
            "cells": len(record.get("results", [])),
            "expected_cells": len(record.get("cases", [])) * len(harnesses),
            "seeds": record.get("config", {}).get("seeds"),
            "skipped": len(record.get("skipped", [])),
            "errors": sum(
                bool(r.get("error") or r.get("gen_error")) for r in record.get("results", [])
            ),
            "evidence_redacted": bool(record.get("publication", {}).get("evidence_redacted")),
            "utility": (record.get("publication", {}).get("utility") or utility_evidence(record))
            if track == "security" else {},
            "rows": rows,
        }

    collections = []
    for collection in manifest["collections"]:
        tracks = []
        for track, selection in collection["tracks"].items():
            if track not in METRICS:
                raise ValueError(f"Unknown historical package track: {track}")
            tracks.append(
                {
                    "track": track,
                    "note": selection.get("note", ""),
                    "primary": source(track, selection["run_id"]),
                    "alternatives": [
                        source(track, rid) for rid in selection.get("alternatives", [])
                    ],
                }
            )
        collections.append(
            {
                "id": collection["id"],
                "title": collection["title"],
                "note": collection.get("note", ""),
                "tracks": tracks,
            }
        )
    return {
        "title": manifest["title"],
        "selection_policy": manifest["selection_policy"],
        "metric_definitions": METRICS,
        "collections": collections,
    }


def sources(package: dict):
    for collection in package["collections"]:
        for track in collection["tracks"]:
            yield collection, track["primary"], "primary"
            for alternative in track["alternatives"]:
                yield collection, alternative, "alternative"


def package_csv(package: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "collection",
            "collection_title",
            "role",
            "track",
            "source_run",
            "harness",
            "model",
            "metric",
            "value",
            "cases",
            "cells",
            "expected_cells",
            "seeds",
            "scoring_version",
            "source_sha256",
            "declared_judge",
            "declared_judge_model",
            "recorded_score_judges",
            "recorded_score_instruments",
            "rescored_from",
            "measurement_status",
            "measurement_note",
        )
    )
    for collection, source, role in sources(package):
        provenance = source["provenance"]
        for row in source["rows"]:
            for metric, value in row["values"].items():
                evidence = source["utility"].get(row["id"], {}) if metric == "secure_useful.rate" else {}
                writer.writerow(
                    (
                        collection["id"],
                        collection["title"],
                        role,
                        source["track"],
                        source["run_id"],
                        row["id"],
                        row["model"],
                        metric,
                        value,
                        source["cases"],
                        source["cells"],
                        source["expected_cells"],
                        source["seeds"],
                        source["scoring_version"],
                        source["source_sha256"],
                        provenance["declared_judge"],
                        provenance["declared_judge_model"],
                        json.dumps(provenance["recorded_score_judges"]),
                        json.dumps(provenance["recorded_score_instruments"]),
                        provenance["rescored_from"],
                        evidence.get("status", "recorded" if value is not None else "unavailable"),
                        evidence.get("note", ""),
                    )
                )
    return output.getvalue()


def _percent(value: float | int | None) -> str:
    return "not recorded" if value is None else f"{value * 100:.1f}%"


def _comparisons(source: dict) -> str:
    comparisons = []
    for group in source.get("asr_groups", []):
        if group["base"] is None or group["cortex"] is None:
            continue
        points = (group["base"] - group["cortex"]) * 100
        direction = "lower" if points >= 0 else "higher"
        comparisons.append(
            f"{escape(group['group'])} pair: <b>{abs(points):.1f} percentage points {direction} "
            f"attack success</b> ({_percent(group['base'])} → {_percent(group['cortex'])})."
        )
    return "<br>".join(comparisons)

def _cell(source: dict, row: dict, path: str) -> str:
    value = _percent(row["values"][path])
    evidence = source["utility"].get(row["id"], {}) if path == "secure_useful.rate" else {}
    if evidence.get("status") in ("unavailable", "unverified"):
        label = "Unavailable" if evidence["status"] == "unavailable" else "Unverified"
        retained = f"<br><small>recorded {value}</small>" if evidence["status"] == "unverified" else ""
        return f'<span title="{escape(evidence["note"])}">{label}</span>{retained}'
    return value



def _source_html(source: dict, *, alternatives: bool = False) -> str:
    metrics = METRICS[source["track"]]
    header = "".join(f"<th>{escape(label)}</th>" for _, label in metrics)
    rows = "".join(
        f"<tr><td>{escape(row['label'])}<br><small>{escape(row['model'] or 'model not recorded')}</small></td>"
        + "".join(f"<td>{_cell(source, row, path)}</td>" for path, _ in metrics)
        + "</tr>"
        for row in source["rows"]
    )
    scoring = source["scoring_version"] or "legacy / unversioned"
    seeds = str(source["seeds"]) if source["seeds"] is not None else "not recorded"
    limits = f"{source['skipped']} skipped · {source['errors']} error cells" + (
        " · captured evidence withheld" if source["evidence_redacted"] else ""
    )
    provenance = source["provenance"]
    utility_notes = sorted({e["note"] for e in source["utility"].values()})
    utility_note = "".join(f'<p class="hint utility-evidence">{escape(note)}</p>' for note in utility_notes)
    body = (
        f'<div class="package-source" data-source-run="{escape(source["run_id"])}">'
        f'<p><a href="{escape(source["href"])}"><b>{escape(source["run_id"])}</b> · open full report</a></p>'
        f'<p class="hint">{source["cases"]} cases × {source["harnesses"]} harnesses · '
        f"{source['cells']}/{source['expected_cells']} recorded cells · seeds: {seeds}<br>"
        f"{escape(source['created_at'] or 'date not recorded')} · scoring: {escape(scoring)} · {limits}</p>"
        '<p class="hint package-provenance">'
        f"Declared judge: {escape(provenance['declared_judge'] or 'not recorded')} · "
        f"methodology model: {escape(provenance['declared_judge_model'] or 'not recorded')}<br>"
        f"Recorded score judges: {escape(', '.join(provenance['recorded_score_judges']) or 'not recorded')} · "
        f"instruments: {escape(', '.join(provenance['recorded_score_instruments']) or 'not recorded')}<br>"
        f"Rescored from: {escape(provenance['rescored_from'] or 'not recorded')}</p>"
        f'<div class="package-table"><table><thead><tr><th>Recorded harness / model</th>{header}</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>{utility_note}<p class="hint">{_comparisons(source)}</p></div>'
    )
    if alternatives:
        return (
            f'<details class="package-alternative"><summary>Alternative: {source["cases"]} cases · '
            f"seeds {seeds} · {source['cells']}/{source['expected_cells']} cells</summary>{body}</details>"
        )
    return body


def render_package(package: dict, track_names: dict[str, tuple]) -> str:
    tracks = []
    jumps = []
    for track, (name, _, _) in track_names.items():
        histories = []
        for collection in package["collections"]:
            selected = next((item for item in collection["tracks"] if item["track"] == track), None)
            if selected is None:
                continue
            histories.append(
                f'<section class="package-collection" id="{escape(collection["id"])}-{escape(track)}">'
                f"<h4>{escape(collection['title'])}</h4><p>{escape(collection['note'])}</p>"
                f'<p class="hint">{escape(selected["note"])}</p>'
                + _source_html(selected["primary"])
                + "".join(_source_html(alt, alternatives=True) for alt in selected["alternatives"])
                + "</section>"
            )
        if histories:
            jumps.append(f'<a href="#package-{escape(track)}">{escape(name)}</a>')
            tracks.append(
                f'<article class="package-track" id="package-{escape(track)}">'
                f"<h3>{escape(name)}</h3>" + "".join(histories) + "</article>"
            )
    return (
        f'<section class="block" id="package"><h2>{escape(package["title"])}</h2>'
        f'<p class="hint">{escape(package["selection_policy"])}</p>'
        f'<nav aria-label="Historical tracks">{" · ".join(jumps)}</nav>'
        "<p>Each track shows its complete modeled reference and captured history separately.</p>"
        '<p><a href="results-package.json" download>Download complete package JSON</a> · '
        '<a href="results-package.csv" download>Download all package measurements as CSV</a></p>'
        + "".join(tracks)
        + "</section>"
    )
