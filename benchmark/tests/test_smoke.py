"""End-to-end smoke: a run yields a valid RunRecord and renders an HTML report."""

import json

from gauntlet.cases import load_security_suite
from gauntlet.report import build_report
from gauntlet.run import run_suite


def test_public_corpus_covers_attack_objectives_without_private_data(monkeypatch):
    monkeypatch.delenv("GAUNTLET_PRIVATE_SECURITY_SCENARIOS", raising=False)
    cases = load_security_suite()
    agentic = [c for c in cases if c.family.startswith("agentic_")]
    hard = [c for c in cases if c.family.startswith("hard_")]
    # both tiers exercise all three harmful objectives (not just secret-exfil)
    assert {c.objective.value for c in agentic} == {"secret_exfil", "malicious_dep", "destructive_git"}
    assert hard and all(c.scaffold_fill > 0 for c in hard)
    assert not any(c.held_out for c in cases)
    # the saturated blatant-exfil obfuscation matrix is gone (no DAN/leetspeak/ascii-art/cipher etc.)
    assert not {c.technique.value for c in cases} & {"roleplay_dan", "leetspeak", "ascii_art", "cipher"}


def test_run_record_is_json_serializable_and_contained():
    rec = run_suite()
    data = json.loads(rec.to_json())
    assert data["containment"]["payloads_executed"] == 0
    assert len(data["results"]) == len(rec.cases) * len(rec.harnesses)


def test_report_renders_self_contained_html(tmp_path):
    rec = run_suite()
    out = tmp_path / "report.html"
    html = build_report(json.loads(rec.to_json()), out)
    assert out.exists()
    assert "<html" in html and "echarts" in html and rec.run_id in html


def test_no_real_secret_leaks_into_record():
    rec = run_suite()
    # The corpus only ever references decoy sinks / example files, never real creds.
    assert "BEGIN PRIVATE KEY" not in rec.to_json()
