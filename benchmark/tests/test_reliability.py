"""pass^k reliability (τ-bench style) for the long-horizon tracks G and P.

Reliability asks not just "did it succeed once" but "does it succeed across k independent runs" —
the single-seed limitation the paper flags. The governed arms should be more reliable than raw.
"""

from gauntlet.generative.run import run_generative_suite
from gauntlet.project.run import DEFAULT_PROJECT_HARNESSES, run_project_suite
from gauntlet.scoring.stats import pass_hat_k


def test_pass_hat_k_identities_and_monotonicity():
    assert pass_hat_k(5, 5, 1) == 1.0 and pass_hat_k(5, 0, 1) == 0.0
    assert abs(pass_hat_k(5, 3, 1) - 0.6) < 1e-9          # pass^1 is the success rate
    assert abs(pass_hat_k(4, 2, 2) - (1 / 6)) < 1e-9      # C(2,2)/C(4,2)
    assert pass_hat_k(5, 2, 3) == 0.0                     # cannot draw 3 successes from 2
    curve = [pass_hat_k(10, 6, k) for k in range(1, 7)]
    assert all(b <= a + 1e-12 for a, b in zip(curve, curve[1:]))  # non-increasing in k


def test_generative_reliability_present_and_governed_leads():
    rec = run_generative_suite(seeds=5, limit=2)
    ph = rec.aggregates["per_harness"]
    for m in ph.values():
        rel = m["reliability"]
        assert rel["k"] == [1, 2, 3, 4, 5]
        assert all(b <= a + 1e-12 for a, b in zip(rel["pass_hat_k"], rel["pass_hat_k"][1:]))
    # the governed arm reliably completes the long horizon where the raw arm does not
    assert ph["cortex_wrapped"]["reliability"]["pass_hat_k"][-1] >= ph["codex_cli_raw"]["reliability"]["pass_hat_k"][-1]


def test_project_seeds_one_parity_and_multi_seed_reliability():
    one = run_project_suite()  # default seeds=1 — unchanged shape
    assert len(one.results) == len(DEFAULT_PROJECT_HARNESSES)  # one result per default harness
    assert set(one.aggregates["per_harness"]) == {h.id for h in one.harnesses}
    assert one.aggregates["per_harness"]["codex_cli_raw"]["reliability"]["k"] == [1]

    many = run_project_suite(seeds=8)
    assert len(many.results) == len(DEFAULT_PROJECT_HARNESSES) * 8  # one result per harness per seed
    ph = many.aggregates["per_harness"]
    # a fully-functional full-repo build is reliable for the governed arm, not for the raw decaying arm
    assert ph["cortex_wrapped"]["reliability"]["success_rate"] > ph["codex_cli_raw"]["reliability"]["success_rate"]
    assert ph["codex_cli_raw"]["reliability"]["n_seeds"] == 8
