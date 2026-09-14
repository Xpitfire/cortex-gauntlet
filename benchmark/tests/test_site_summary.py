"""Tests for the investor summary: relative-gain framing, base-model grouping, parity filtering,
favicon/logo, the renamed labels, and the docs appendix."""

import json
import re

from gauntlet import site
from gauntlet.models import SCHEMA_VERSION, SCORING_VERSION


def test_relative_gain_framing():
    # lower-is-better (jailbreaks): 26% -> 6.7% is a ~74% relative reduction
    assert round(site._rel(0.26, 0.067, lower_is_better=True) * 100) == 74
    # higher-is-better (coverage): 0.34 -> 0.91 is a ~168% relative uplift
    assert round(site._rel(0.34, 0.91, lower_is_better=False) * 100) == 168
    assert site._rel(0.0, 0.5, lower_is_better=True) is None  # no divide-by-zero
    assert site._rel(0.5, None, lower_is_better=True) is None


def _security_record() -> dict:
    def ph(rate):
        return {"asr": {"rate": rate, "n": 1000}}

    return {
        "track": "security",
        "harnesses": [
            {"id": h}
            for h in ("codex_cli_raw", "claude_code", "opencode", "cortex_wrapped", "cortex_claude")
        ],
        "aggregates": {
            "harness_delta": {
                "raw": "codex_cli_raw",
                "cortex_wrapped": "cortex_wrapped",
                "asr": {"raw": 0.26, "cortex_wrapped": 0.067, "delta": 0.193},
            },
            "per_harness": {
                "codex_cli_raw": ph(0.26),
                "claude_code": ph(0.137),
                "opencode": ph(0.186),
                "cortex_wrapped": ph(0.067),
                "cortex_claude": ph(0.07),
            },
        },
    }


def test_asr_groups_split_by_base_model():
    groups = {g["group"]: g for g in site._asr_groups(_security_record())}
    assert groups["Codex"]["base"] == 0.26 and groups["Codex"]["cortex"] == 0.067
    assert groups["Claude"]["base"] == 0.137 and groups["Claude"]["cortex"] == 0.07
    assert groups["OpenCode"]["cortex"] is None  # OSS reference has no Cortex pairing


def test_empty_security_denominator_is_not_a_measured_zero():
    record = _security_record()
    per_harness = record["aggregates"]["per_harness"]
    per_harness["cortex_wrapped"]["asr"] = {"rate": 0.0, "n": 0}
    per_harness["cortex_claude"]["asr"] = {"rate": 0.0, "n": 10}

    groups = {g["group"]: g for g in site._asr_groups(record)}

    assert groups["Codex"]["cortex"] is None
    assert groups["Claude"]["cortex"] == 0.0
    assert site._track_delta(record)["rel"] is None
    assert per_harness["cortex_wrapped"]["asr"] == {"rate": 0.0, "n": 0}


def test_summary_rejects_historical_run_without_qualification():
    rid = "security-x"
    summary = site._summary({rid: _security_record()}, {"security": rid})
    assert summary["lead"] is None
    assert summary["avg_rel"] is None
    assert summary["stats"] == []


def test_parity_track_is_not_shown_as_a_weak_stat():
    # raw == cortex coverage → relative gain 0 → must NOT appear as a headline stat
    rid = "quality-x"
    # _headline gates on qualification first, so the record must carry the current schema/scoring
    # versions and be a live run — otherwise it is described as "non-qualifying" and the parity
    # wording under test is never reached.
    rec = {
        "track": "quality",
        "schema_version": SCHEMA_VERSION,
        "scoring_version": SCORING_VERSION,
        "config": {"live": True},
        "harnesses": [{"id": "codex_cli_raw"}, {"id": "cortex_wrapped"}],
        "cases": [{"id": "task"}],
        "results": [
            {"task_id": "task", "harness_id": hid} for hid in ("codex_cli_raw", "cortex_wrapped")
        ],
        "aggregates": {
            "synapse_delta": {"raw": "codex_cli_raw", "cortex_wrapped": "cortex_wrapped"},
            "per_harness": {
                "codex_cli_raw": {"requirement_coverage": 1.0},
                "cortex_wrapped": {"requirement_coverage": 1.0},
            },
        },
    }
    summary = site._summary({rid: rec}, {"quality": rid})
    assert all(s["track"] != "quality" for s in summary["stats"])  # parity not led with


def test_navbar_degrades_for_standalone_reports():
    from gauntlet.report_common import navbar

    # standalone single-run report (no site links) → minimal bar, NO cross-track links that would 404
    bare = navbar("../../index.html", "Security", links=None)
    assert 'class="lnk' not in bare and "index.html" not in bare
    assert 'class="brand" href="#"' in bare and 'id="themeBtn"' in bare
    # built-site context (links provided) → full, resolvable nav including Docs
    full = navbar(
        "index.html", "Paper", links={"Security": "runs/s/report.html", "Paper": "docs.html"}
    )
    assert 'href="runs/s/report.html"' in full and 'href="docs.html"' in full


def test_all_historical_tracks_remain_navigable_without_qualifying_headlines(tmp_path, monkeypatch):
    results, public = tmp_path / "results", tmp_path / "public"
    monkeypatch.setattr(site, "RESULTS", results)
    monkeypatch.setattr(site, "DIST", public)
    tracks = ("security", "quality", "generative", "project", "repo")
    manifest = tmp_path / "package.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Historical package",
                "selection_policy": "Explicit historical sources",
                "collections": [
                    {
                        "id": "historical",
                        "title": "Historical",
                        "tracks": {track: {"run_id": f"{track}-historical"} for track in tracks},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(site, "PACKAGE_FILE", manifest, raising=False)
    for track in tracks:
        run_dir = results / f"{track}-historical"
        run_dir.mkdir(parents=True)
        record = {
            "run_id": run_dir.name,
            "track": track,
            "created_at": "2020-01-01",
            "config": {"live": False},
            "cases": [{"id": "case"}],
            "harnesses": [{"id": "fixture"}],
            "results": [{"case_id": "case", "harness_id": "fixture"}],
            "aggregates": {},
        }
        (run_dir / "runrecord.json").write_text(json.dumps(record))
        diagnostic = {**record, "run_id": f"{track}-diagnostic", "created_at": "2030-01-01"}
        diagnostic_dir = results / diagnostic["run_id"]
        diagnostic_dir.mkdir()
        (diagnostic_dir / "runrecord.json").write_text(json.dumps(diagnostic))

    site.build_site()

    results_page = (public / "results.html").read_text()
    paper = (public / "docs.html").read_text()
    archive = results_page.split('id="results"', 1)[1].split('id="indexBlock"', 1)[0]
    for track in tracks:
        target = f"runs/{track}-historical/report.html"
        assert f'href="{target}"' in archive
        category = "bugfix" if track == "repo" else track
        assert f'href="{category}.html"' in paper and (public / f"{category}.html").is_file()
        assert (public / target).is_file()
        assert f'href="runs/{track}-diagnostic/report.html"' in archive
        assert f'href="runs/{track}-diagnostic/report.html"' not in paper
        diagnostic = (public / "runs" / f"{track}-diagnostic" / "report.html").read_text()
        context = diagnostic.split('class="publication-note package-note"', 1)[1].split(
            "</aside>", 1
        )[0]
        assert f'href="../../{category}.html"' in context
        package_html = results_page.split('id="package"', 1)[1].split('id="results"', 1)[0]
        assert f'data-source-run="{track}-historical"' in package_html
        assert f'data-source-run="{track}-diagnostic"' not in package_html
    summary = json.loads(
        re.search(r'<script id="summary" type="application/json">(.*?)</script>', results_page, re.DOTALL)[
            1
        ]
    )
    assert summary["lead"] is None and summary["avg_rel"] is None and summary["stats"] == []


def test_paper_navigation_updates_preserve_content_and_its_publication_date(tmp_path):
    path = tmp_path / "docs.html"
    original = site._build_paper(path, {"Results": "index.html", "Paper": "docs.html"})
    stamp = r"(?<=generated )\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?=\.</footer>)"
    original = re.sub(stamp, "2000-01-01T00:00:00", original)
    path.write_text(original)
    links = {"Overview": "index.html", "Results": "results.html", "Paper": "docs.html"}
    updated = site._build_paper(path, links)
    nav = r"<nav\b[^>]*>.*?</nav>"
    assert re.sub(nav, "", updated, count=1, flags=re.DOTALL) == re.sub(
        nav, "", original, count=1, flags=re.DOTALL
    )
    assert 'href="results.html"' in updated

    # An outdated body must still be regenerated, not preserved as a stale cache.
    path.write_text(updated.replace("<footer>", "<p>Outdated publication body.</p><footer>", 1))
    refreshed = site._build_paper(path, links)
    assert re.sub(stamp, "", refreshed) == re.sub(stamp, "", updated)
    assert re.search(stamp, refreshed)[0] != "2000-01-01T00:00:00"
