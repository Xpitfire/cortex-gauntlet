"""Tests for the VERTEX cross-similarity scorer (deterministic via the hashing fallback)."""

from gauntlet.analysis.vertex import vertex_score

REF = [
    "home page with header, category navigation, search and cart",
    "category listing page with a responsive product grid",
    "product detail page with image, price and size selection",
    "add to cart from the product page",
    "cart with editable quantities and correct totals",
    "checkout flow reaching a payment step",
    "stripe test-mode payment with a test card",
    "order confirmation page after payment",
]


def _score(cand, **kw):
    return vertex_score(cand, REF, model=None, **kw)  # model=None forces the deterministic fallback


def test_identical_trajectory_scores_high():
    s = _score(list(REF))
    assert s.backend == "hash-fallback"
    assert s.vertex > 0.6
    assert s.recall > 0.9


def test_partial_trajectory_scores_between():
    full = _score(list(REF))
    partial = _score(REF[:3])  # only the first three capabilities
    assert partial.vertex < full.vertex
    assert partial.recall < full.recall  # missing capabilities hurt recall


def test_disjoint_trajectory_scores_low():
    disjoint = _score(["unrelated database migration tool", "kubernetes yaml linter", "a poem about rain"])
    full = _score(list(REF))
    assert disjoint.vertex < full.vertex
    assert disjoint.vertex < 0.5


def test_ordered_penalty_rewards_coherent_order():
    forward = _score(list(REF))
    reversed_traj = _score(list(reversed(REF)))
    # same set of capabilities → similar unordered F, but the ordered (DTW-decay) view prefers order
    assert forward.ordered >= reversed_traj.ordered
    assert abs(forward.f_unordered - reversed_traj.f_unordered) < 0.05


def test_empty_is_zero():
    assert vertex_score([], REF, model=None).vertex == 0.0
    assert vertex_score(list(REF), [], model=None).vertex == 0.0


def test_scores_are_bounded_and_deterministic():
    a = _score(REF[:5])
    b = _score(REF[:5])
    assert a == b  # deterministic
    for value in (a.vertex, a.f_unordered, a.ordered, a.precision, a.recall):
        assert 0.0 <= value <= 1.0
