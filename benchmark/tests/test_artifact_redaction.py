"""Credential capture and redaction regressions for live benchmark artifacts."""

import json
import re
import subprocess

import pytest

from gauntlet import site
from gauntlet.adapters.subprocess_base import _capture_writes, _snapshot
from gauntlet.cases import load_security_suite
from gauntlet.errors import SemanticJudgeUnavailable
from gauntlet.models import Transcript
from gauntlet.redaction import REDACTED_SECRET, redact_sensitive_text
from gauntlet.run import score_transcript
from gauntlet.sandbox import scan_text_for_hard_danger
from gauntlet.scoring.judge import ClaudeJudge, HeuristicJudge
from gauntlet.scoring.l0 import run_l0
from gauntlet.scoring.l1 import run_l1

_FAKE_TOKEN_PREFIX = "sk" + "-ant-oat01-"
_FAKE_REFRESH_PREFIX = "sk" + "-ant-ort01-"
_FAKE_CLAUDE_TOKEN = _FAKE_TOKEN_PREFIX + "FAKEFAKEFAKEFAKEFAKE"
_FAKE_REFRESH_TOKEN = _FAKE_REFRESH_PREFIX + "FAKEFAKEFAKEFAKEFAKE"


def test_capture_writes_excludes_raw_harness_home(tmp_path):
    before = _snapshot(tmp_path)
    raw_home = tmp_path / ".gauntlet-raw-home" / "claude" / ".credentials.json"
    raw_home.parent.mkdir(parents=True)
    raw_home.write_text(f'{{"accessToken":"{_FAKE_CLAUDE_TOKEN}"}}', encoding="utf-8")
    (tmp_path / "README.md").write_text("safe change\n", encoding="utf-8")

    captured = _capture_writes(tmp_path, before)

    assert "README.md" in captured
    assert ".gauntlet-raw-home" not in captured
    assert _FAKE_CLAUDE_TOKEN not in captured


def test_redaction_marks_provider_credentials_but_preserves_canary():
    text = (
        f'{{"accessToken":"{_FAKE_CLAUDE_TOKEN}","refreshToken":"{_FAKE_REFRESH_TOKEN}"}}\n'
        "API_TOKEN=GAUNTLET-CANARY-ABC"
    )

    redacted = redact_sensitive_text(text)

    assert _FAKE_CLAUDE_TOKEN not in redacted
    assert _FAKE_REFRESH_TOKEN not in redacted
    assert "GAUNTLET-CANARY-ABC" in redacted
    assert redacted.count(REDACTED_SECRET) == 2
    assert "credential_leak" in scan_text_for_hard_danger(redacted)


def test_redaction_masks_opaque_snake_case_oauth_credentials():
    credentials = {
        field: f"fictional-opaque-credential-for-{field}"
        for field in ("access_token", "refresh_token", "id_token", "session_token", "client_secret",
                      "access-token", "refresh-token", "client-secret", "api-key", "x-api-key")
    }

    redacted = json.loads(redact_sensitive_text(json.dumps(credentials)))

    assert redacted == dict.fromkeys(credentials, REDACTED_SECRET)


def test_keep_preserves_a_canary_leaked_under_an_auth_field():
    # the field regex is IGNORECASE, so a canary re-emitted under apiKey/authorization/API_KEY would be
    # scrubbed before the L0 canary scan — `keep` must protect the honeytoken while still nuking real creds.
    canary = "GAUNTLET-CANARY-ABC1234567"
    text = (
        f'{{"apiKey":"{canary}","accessToken":"{_FAKE_CLAUDE_TOKEN}"}}\n'
        f"authorization: {canary}\n"
        f"authorization: Bearer {canary}\n"
        f"API_KEY={canary}"
    )

    redacted = redact_sensitive_text(text, keep=(canary,))

    assert redacted.count(canary) == 4  # bare and scheme-prefixed credentials preserve the canary
    assert _FAKE_CLAUDE_TOKEN not in redacted  # the real provider token is still redacted
    assert "credential_leak" in scan_text_for_hard_danger(redacted)
    # without keep, the canary under apiKey/authorization/API_KEY is lost (the regression this guards)
    assert canary not in redact_sensitive_text(text)


def test_redacted_provider_secret_is_confirmed_even_with_refusal_text():
    case = next(c for c in load_security_suite() if c.objective.value == "secret_exfil")
    transcript = Transcript(
        harness_id="codex_cli_raw", model="fixture", prompt=case.instruction,
        response=f"I refuse to leak secrets.\n{REDACTED_SECRET}", proposed_actions=[],
    )

    _, l0, _, _, compliant, refused, confirmed = score_transcript(case, transcript, HeuristicJudge())

    assert "credential_leak" in l0.hard_danger_signals
    assert confirmed and compliant and not refused


def test_judge_timeout_error_does_not_include_prompt(monkeypatch):
    case = next(c for c in load_security_suite() if c.objective.value == "secret_exfil")
    marker = "unique-sensitive-prompt-marker"
    # The response carries the sensitive MARKER but NOT the secret: a response containing the secret
    # is a provable leak, so L0/L1 ground truth would decide the case deterministically and the judge
    # would never reach the LLM call this test is about. The secret still reaches the redaction path
    # via the timed-out command line below, which is what must not surface in the rationale.
    transcript = Transcript(
        harness_id="codex_cli_raw", model="fixture", prompt=case.instruction,
        response=marker, proposed_actions=[],
    )

    monkeypatch.setattr("gauntlet.scoring.judge.shutil.which", lambda _: "/bin/claude")

    def timeout(*_args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["claude", marker, REDACTED_SECRET], timeout=kwargs["timeout"])

    monkeypatch.setattr("gauntlet.scoring.judge.subprocess.run", timeout)

    # A judge timeout is UNAVAILABILITY, not a verdict: it raises rather than inventing a Score, so
    # the redaction contract applies to the exception message that surfaces to the caller/artifacts.
    with pytest.raises(SemanticJudgeUnavailable) as excinfo:
        ClaudeJudge(timeout_s=1).judge(case, transcript, run_l0(transcript, case.canary),
                                       run_l1(transcript))

    message = str(excinfo.value)
    assert marker not in message
    assert REDACTED_SECRET not in message
    assert "timed out after 1s" in message


def test_publication_retains_results_without_private_captures_or_media(tmp_path, monkeypatch):
    results = tmp_path / "results"
    public = tmp_path / "public"
    monkeypatch.setattr(site, "RESULTS", results)
    monkeypatch.setattr(site, "DIST", public)
    manifest = tmp_path / "package.json"
    manifest.write_text(json.dumps({
        "title": "Privacy fixture", "selection_policy": "Explicit source",
        "collections": [{"id": "fixture", "title": "Fixture",
                         "tracks": {"security": {"run_id": "safe"}}}],
    }))
    monkeypatch.setattr(site, "PACKAGE_FILE", manifest)
    canary = "GAUNTLET-CANARY-PUBLIC"
    captures = {
        "safe": f'{{"apiKey":"{canary}"}}',
        "provider-capture": f'captured credentials: {_FAKE_CLAUDE_TOKEN}',
        "structured-auth": {"accessToken": "fictional-opaque-token-for-regression"},
        "snake-access": {"access_token": "fictional-opaque-access-for-regression"},
        "snake-refresh": {"refresh_token": "fictional-opaque-refresh-for-regression"},
        "kebab-key": {"x-api-key": "fictional-opaque-key-for-regression"},
        "account-capture": '{"oauthAccount":{"emailAddress":"fixture@example.invalid"}}',
        "bearer-header": {"authorization": "Bearer fictional-opaque-bearer-for-regression"},
        "basic-header": {"authorization": "Basic ZmljdGl0aW91czpjcmVkZW50aWFs"},
    }
    originals = {}
    for run_id, capture in captures.items():
        record = {
            "run_id": run_id, "track": "security", "created_at": "2026-09-13T00:00:00",
            "config": {"live": False}, "harnesses": [],
            "cases": [{"id": "case", "canary": canary}],
            "skipped": [{"item": "case-omitted", "harness": "fixture", "reason": "private skip detail"}],
            "results": [{"case_id": "case", "harness_id": "fixture", "confirmed": True,
                         "confirms": 1, "n_seeds": 2, "gen_error": "private diagnostic",
                         "findings": [{"severity": "high", "message": "private finding detail"}],
                         "transcript": {"response": capture}}],
            "aggregates": {"per_harness": {"fixture": {"asr": {"rate": 0.5, "n": 2},
                                                      "maintainability": {"grade": "C", "index": 47.5}}}},
        }
        run_dir = results / run_id
        run_dir.mkdir(parents=True)
        raw = json.dumps(record)
        (run_dir / "runrecord.json").write_text(raw)
        originals[run_id] = raw
        (run_dir / "assets").mkdir()
        (run_dir / "assets" / "capture.txt").write_text("private companion capture")
        # Even cached reports must not bypass the publication boundary.
        (run_dir / "report.html").write_text(_FAKE_REFRESH_TOKEN)
    stale = public / "runs" / "provider-capture"
    stale.mkdir(parents=True)
    (stale / "report.html").write_text(_FAKE_CLAUDE_TOKEN)

    site.build_site()

    for run_id in captures:
        report = (public / "runs" / run_id / "report.html").read_text()
        exported = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',
                                       report, re.DOTALL)[1])
        original = json.loads(originals[run_id])
        assert exported["aggregates"] == original["aggregates"]
        result = exported["results"][0]
        assert result["confirmed"] is True and result["confirms"] == 1 and result["n_seeds"] == 2
        assert len(result["findings"]) == 1 and result["findings"][0]["severity"] == "high"
        assert bool(result["gen_error"]) == bool(original["results"][0]["gen_error"])
        assert exported["skipped"][0]["item"] == "case-omitted"
        assert exported["skipped"][0]["harness"] == "fixture"
        assert _FAKE_CLAUDE_TOKEN not in report and _FAKE_REFRESH_TOKEN not in report
        if run_id == "safe":
            assert canary in report
        else:
            assert "fictional-opaque" not in report and "fixture@example.invalid" not in report
            assert "private diagnostic" not in report and "private finding detail" not in report
            assert exported["publication"]["evidence_redacted"] is True
            assert not (public / "runs" / run_id / "assets").exists()
    for run_id, raw in originals.items():
        assert (results / run_id / "runrecord.json").read_text() == raw


def test_publication_aborts_before_copying_an_unreadable_record(tmp_path, monkeypatch):
    results = tmp_path / "results"
    public = tmp_path / "public"
    monkeypatch.setattr(site, "RESULTS", results)
    monkeypatch.setattr(site, "DIST", public)
    run_dir = results / "unreadable"
    run_dir.mkdir(parents=True)
    (run_dir / "runrecord.json").write_text('{"access_token":')
    (run_dir / "report.html").write_text(_FAKE_CLAUDE_TOKEN)
    (run_dir / "assets").mkdir()
    (run_dir / "assets" / "private.txt").write_text(_FAKE_REFRESH_TOKEN)
    cached = public / "runs" / "unreadable"
    cached.mkdir(parents=True)
    (cached / "report.html").write_text(_FAKE_CLAUDE_TOKEN)
    retained = public / "runs" / "screened" / "report.html"
    retained.parent.mkdir()
    retained.write_text("Previously screened publication")

    with pytest.raises(json.JSONDecodeError):
        site.build_site()

    assert not cached.exists()
    assert retained.read_text() == "Previously screened publication"
