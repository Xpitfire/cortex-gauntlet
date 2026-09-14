"""The safety/utility tradeoff on Track S (AgentDojo / CyberSecEval framing).

Reporting attack-success alone can be gamed by refusing everything; the secure∧useful metric credits
a harness only when it both resists the injection AND still completes the benign carrier task. Cortex
should lead here, because governance blocks the unsafe action class without suppressing the legit task.
"""

from gauntlet.run import run_suite


def test_secure_useful_metric_present_and_bounded():
    agg = run_suite().aggregates
    for hid, m in agg["per_harness"].items():
        su = m["secure_useful"]
        assert 0.0 <= su["rate"] <= 1.0 and su["n"] > 0, hid
        # secure∧useful can never exceed plain utility-under-attack (it is a stricter conjunction)
        assert su["rate"] <= m["utility_under_attack"]["rate"] + 1e-9


def test_cortex_leads_on_the_tradeoff():
    d = run_suite().aggregates["harness_delta"]
    assert "secure_useful" in d
    # higher is better here; the delta is raw − cortex, so a governed lead shows as delta <= 0
    assert d["secure_useful"]["cortex_wrapped"] >= d["secure_useful"]["raw"]
