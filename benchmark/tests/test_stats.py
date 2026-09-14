"""Reproducibility statistics: pass@k estimator, Wilson, bootstrap determinism."""

from gauntlet.scoring.stats import bootstrap_ci, mean, pass_at_k, std, wilson_interval


def test_pass_at_k_edges_and_known_values():
    assert pass_at_k(5, 0, 1) == 0.0  # no success -> 0
    assert pass_at_k(5, 5, 1) == 1.0  # all success -> 1
    assert abs(pass_at_k(5, 1, 1) - 0.2) < 1e-9  # 1/5 with k=1
    assert pass_at_k(5, 1, 5) == 1.0  # any 5 draws from 5 include the success
    assert abs(pass_at_k(4, 1, 2) - 0.5) < 1e-9  # 1 - C(3,2)/C(4,2) = 0.5


def test_pass_at_k_monotone_in_k():
    vals = [pass_at_k(10, 2, k) for k in range(1, 11)]
    assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))


def test_wilson_bounds():
    lo, hi = wilson_interval(5, 10)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    assert wilson_interval(0, 0) == (None, None)


def test_bootstrap_is_deterministic_with_fixed_seed():
    values = [0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.2, 0.8]
    assert bootstrap_ci(values, seed=0) == bootstrap_ci(values, seed=0)
    lo, hi = bootstrap_ci(values, seed=0)
    assert 0.0 <= lo <= mean(values) <= hi <= 1.0


def test_mean_and_std():
    assert mean([]) == 0.0 and std([1.0]) == 0.0
    assert abs(mean([0.0, 1.0]) - 0.5) < 1e-9
    assert std([0.0, 1.0]) > 0.0
