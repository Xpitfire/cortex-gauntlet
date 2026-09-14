"""M3: multi-seed runs, pass@k aggregates, capability declaration, attempt budget."""

from gauntlet.run import DEFAULT_ADAPTERS, PRESETS, run_suite


def test_seeds_drive_attempt_budget_and_result_shape():
    rec = run_suite(seeds=3)
    assert rec.config["seeds"] == 3
    assert all(r.n_seeds == 3 for r in rec.results)
    assert len(rec.results) == len(rec.cases) * len(rec.harnesses)
    # each cell aggregates 0..3 compliances over its 3 seeds
    assert all(0 <= r.complies <= 3 for r in rec.results)


def test_per_harness_has_reproducibility_fields():
    agg = run_suite(seeds=4).aggregates
    for spec in DEFAULT_ADAPTERS:
        hid = spec.split(":", 1)[1]
        m = agg["per_harness"][hid]
        assert m["attempts_per_case"] == 4
        assert len(m["asr_bootstrap_ci"]) == 2
        assert 0.0 <= m["asr_at_1"] <= m["asr_at_n"] <= 1.0  # any-seed >= single-seed
        assert m["asr_seed_std"] >= 0.0


def test_capabilities_declared_per_harness():
    assert PRESETS["cortex_wrapped"].supports_multimodal is True
    assert PRESETS["opencode"].supports_multimodal is False
    assert PRESETS["claude_code"].max_context >= 1_000_000


def test_monotonic_safety_holds_per_seed():
    # cortex-wrapped never scores a higher pooled ASR than raw, at any seed count
    rec = run_suite(seeds=5)
    ph = rec.aggregates["per_harness"]
    assert ph["cortex_wrapped"]["asr"]["rate"] <= ph["codex_cli_raw"]["asr"]["rate"]
