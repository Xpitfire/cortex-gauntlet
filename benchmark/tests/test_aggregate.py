"""Aggregation: Wilson interval bounds and end-to-end metric shape."""

from gauntlet.run import DEFAULT_ADAPTERS, run_suite
from gauntlet.scoring.aggregate import wilson_interval


def test_wilson_bounds_are_sane():
    lo, hi = wilson_interval(5, 10)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    assert wilson_interval(0, 0) == (None, None)


def test_run_produces_per_harness_and_delta():
    rec = run_suite()
    agg = rec.aggregates
    for spec in DEFAULT_ADAPTERS:
        hid = spec.split(":", 1)[1]
        assert hid in agg["per_harness"]
        assert 0.0 <= agg["per_harness"][hid]["asr"]["rate"] <= 1.0
    assert "asr" in agg["harness_delta"]


def test_cortex_wrapped_reduces_asr_vs_raw():
    rec = run_suite()
    d = rec.aggregates["harness_delta"]["asr"]
    # Cortex-wrapped should not be less safe than raw in the offline model.
    assert d["cortex_wrapped"] <= d["raw"]
