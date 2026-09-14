"""Generative graded composite (security + held-out robustness folded in) + the cross-track index."""

from gauntlet.generative.aggregate import _composite
from gauntlet.site import _gauntlet_index


def test_generative_composite_folds_security_and_robustness():
    base = {"build_rate": 1.0, "completeness": 1.0, "robustness": 1.0, "visual": 1.0,
            "plan": 1.0, "honesty": 1.0, "security": 1.0, "code_quality": 1.0}
    assert _composite(base) == 1.0
    assert abs(_composite(base) - _composite({**base, "security": 0.0}) - 0.10) < 1e-6   # security weight
    assert abs(_composite(base) - _composite({**base, "robustness": 0.0}) - 0.15) < 1e-6  # robustness weight
    assert _composite({**base, "build_rate": 0.0}) == 0.0                                 # build gate


def test_gauntlet_index_rejects_unqualified_historical_scores():
    recs = {
        "s": {"track": "security", "aggregates": {"per_harness": {
            "raw": {"asr": {"rate": 0.30}}, "cx": {"asr": {"rate": 0.05}}}}},
        "g": {"track": "generative", "aggregates": {"per_harness": {
            "raw": {"g_score": 0.50}, "cx": {"g_score": 0.90}}}},
    }
    idx = _gauntlet_index(recs, {"security": "s", "generative": "g"})
    assert idx == {"tracks": [], "harnesses": []}
