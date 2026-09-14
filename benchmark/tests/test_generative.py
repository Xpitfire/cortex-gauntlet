"""Track G: corpus, long-horizon decay, Synapse completeness uplift, screenshot, report."""

import http.server
import json
import socket
import threading

from gauntlet.generative.corpus import load_briefs
from gauntlet.generative.generate import run_brief
from gauntlet.generative.judge import HeuristicGenerativeJudge
from gauntlet.generative.run import run_generative_suite
from gauntlet.generative.screenshot import render
from gauntlet.run import PRESETS
from gauntlet.synapse import SynapsePlanner


def _run(harness_id):
    brief = load_briefs()[0]  # e-commerce, 12 features
    return brief, run_brief(brief, PRESETS[harness_id], SynapsePlanner(), HeuristicGenerativeJudge(), 8)


def test_corpus_loads_briefs_with_features():
    briefs = load_briefs()
    assert briefs and all(len(b.features) >= 10 for b in briefs)
    assert any(b.mandated_stack for b in briefs)


def test_raw_harness_decays_over_the_horizon():
    _, res = _run("codex_cli_raw")
    rates = [c / res.n_seeds for c in res.feature_pass_counts]
    third = len(rates) // 3
    early = sum(rates[:third]) / third
    late = sum(rates[-third:]) / third
    assert early > late  # later features are dropped more by the raw harness


def test_synapse_stays_flat_and_more_complete():
    _, raw = _run("codex_cli_raw")
    _, syn = _run("cortex_wrapped")
    raw_c = sum(raw.seed_completeness) / raw.n_seeds
    syn_c = sum(syn.seed_completeness) / syn.n_seeds
    assert syn_c > raw_c
    # Synapse keeps late features nearly as complete as early ones
    rates = [c / syn.n_seeds for c in syn.feature_pass_counts]
    assert min(rates) >= 0.6


def test_synapse_is_honest_raw_overclaims():
    _, raw = _run("codex_cli_raw")
    _, syn = _run("cortex_wrapped")
    assert syn.honesty >= raw.honesty
    assert syn.honesty == 1.0  # claims == passes (validated)


def test_aggregate_and_delta():
    agg = run_generative_suite(seeds=5).aggregates
    ph = agg["per_harness"]
    assert len(ph["codex_cli_raw"]["horizon_curve"]) == 10
    assert ph["cortex_wrapped"]["completeness"] > ph["codex_cli_raw"]["completeness"]
    assert agg["synapse_delta"]["completeness"]["delta"] > 0
    assert 0.0 <= ph["cortex_wrapped"]["g_score"] <= 1.0


def test_screenshot_renders_svg(tmp_path):
    brief, res = _run("cortex_wrapped")
    rel = render(brief, res, tmp_path)
    asset = tmp_path / f"{brief.id}-cortex_wrapped.svg"
    assert rel.endswith(".svg") and asset.exists() and "features" in asset.read_text()




def _serve_chat(reply: str) -> str:
    """A fake app /api/chat that returns `reply` (200) — to test the chat e2e check's pass/fail."""

    class _App(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: ANN002, ANN202 — quiet
            pass

        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("content-length", 0)))
            body = json.dumps({"reply": reply}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    srv = http.server.HTTPServer(("127.0.0.1", port), _App)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"


def test_chat_check_requires_a_real_round_trip_not_a_graceful_error():
    # the 7/7 false positive: the chat check passed on status 200 + ANY non-empty text, so an
    # "I could not reach the local model" error counted as a working chat. With expect="pong" it must
    # require the reply to reflect a real round-trip (the stub echoes the prompt / a real SLM obeys it).
    from gauntlet.generative.e2e import _chat_check

    chk = {"id": "send-message", "path": "/api/chat",
           "message": "Reply with the single word: pong", "expect": "pong", "timeout": 10}
    real = _chat_check(_serve_chat("pong"), chk)
    err = _chat_check(_serve_chat("I could not reach the local language model. Check LLM_BASE_URL."), chk)
    assert real.passed, "a real pong reply must pass"
    assert not err.passed, "a graceful 'could not reach the model' error must NOT pass (was the 7/7 bug)"


def test_chat_brief_states_the_llm_integration_contract():
    # the apps failed with 'Connection refused' because the brief never told them how to reach the LLM.
    # the contract must name LLM_BASE_URL/LLM_MODEL and the probed endpoints so a correct app is testable.
    brief = next(b for b in load_briefs() if b.id == "chat-clone")
    for token in ("LLM_BASE_URL", "LLM_MODEL", "/api/chat", "/static/"):
        assert token in brief.instruction, f"brief must specify {token} so functionality is testable"
