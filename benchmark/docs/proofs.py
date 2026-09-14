"""Selected symbolic identities and finite examples from the Gauntlet / Cortex paper.

Run from benchmark/: `.venv/bin/python docs/proofs.py` (needs only sympy).
These checks are not general theorem proofs, runtime verification, or empirical evidence:

  P1 baseline normalization n(x,b)=(x-b)/(1-b) maps [b,1]->[0,1], monotone  (analysis/vertex.py:_normalize)
  P2 build-gated composite is a convex combination -> in [min s_k, max s_k] ⊆ [0,1]  (project/score.py)
  P3 BERTScore-style F = 2PR/(P+R) ∈ [0,1], min(P,R) ≤ F ≤ max(P,R)            (analysis/vertex.py:_unordered_f)
  P4 DTW-decay similarity D = max(0, 1 - cost/(m+n)) ∈ [0,1]                   (analysis/vertex.py:_dtw_decay)
  P5 pass@k = 1 - C(n-c,k)/C(n,k) equals 1 - P(zero pass in k draws), ∈[0,1], ↑ in k   (scoring)
  P6 Wilson score interval bounds are exactly the roots of the score equation (p̂-p)²=z²p(1-p)/n
  P7 one monotone, inflationary prerequisite lattice: ≤ |R| strict increases from ∅;
     one extra evaluation detects equality; repeated full sweeps are fair schedules.
  P8 geometric waiting identity and a finite chain attaining the conditional completion bound.
"""

from __future__ import annotations

import ast
from itertools import combinations, permutations
from pathlib import Path

import sympy as sp

CHECKS: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    CHECKS.append((name, bool(ok)))


# ---- P1 — baseline normalization maps [b,1] -> [0,1], monotone, fixed endpoints ----------------
def p1_normalization() -> None:
    x, b = sp.symbols("x b", real=True)
    n = (x - b) / (1 - b)
    check("P1 n(b,b)=0", sp.simplify(n.subs(x, b)) == 0)
    check("P1 n(1,b)=1", sp.simplify(n.subs(x, 1)) == 1)
    # strictly increasing in x for b<1
    check("P1 dn/dx > 0 for b<1", sp.simplify(sp.diff(n, x) - 1 / (1 - b)) == 0)
    # endpoints + monotonicity ⇒ n([b,1]) = [0,1]; clamp(max(0,min(1,·))) keeps it in [0,1] elsewhere
    check("P1 monotone factor 1/(1-b) positive for b in [0,1)",
          all((1 / (1 - bv)) > 0 for bv in (sp.Rational(0), sp.Rational(1, 2), sp.Rational(99, 100))))


# ---- P2 — build-gated composite is a convex combination, hence bounded by its signals ----------
def p2_composite() -> None:
    # Read the canonical literal without importing the scorer or its optional dependencies.
    source = Path(__file__).resolve().parents[1] / "gauntlet" / "project" / "score.py"
    declarations = [
        node.value for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "WEIGHTS" for target in node.targets)
    ]
    declaration, = declarations  # require exactly one top-level definition; never fall back to a copy
    weights = ast.literal_eval(declaration)
    w = {key: sp.Rational(str(value)) for key, value in weights.items()}
    check("P2 weights sum to 1", sum(w.values()) == 1)
    check("P2 weights nonnegative", all(v >= 0 for v in w.values()))
    # for s_k ∈ [0,1]: composite = Σ w_k s_k ∈ [0,1]; lower bound at s=0, upper at s=1
    s = {k: sp.Symbol(f"s_{k}", nonnegative=True) for k in w}
    comp = sum(w[k] * s[k] for k in w)
    check("P2 composite at s=1 equals 1", sp.simplify(comp.subs({s[k]: 1 for k in w})) == 1)
    check("P2 composite at s=0 equals 0", sp.simplify(comp.subs({s[k]: 0 for k in w})) == 0)
    # build gate: multiply by indicator g∈{0,1}; g=0 zeroes the composite
    g = sp.Symbol("g")
    check("P2 build gate g=0 zeroes composite", sp.simplify((g * comp).subs(g, 0)) == 0)


# ---- P3 — F = harmonic mean of precision/recall is in [0,1] and between min and max ------------
def p3_fscore() -> None:
    p, r = sp.symbols("p r", positive=True)
    f = 2 * p * r / (p + r)
    # F = P when P = R
    check("P3 F(p,p)=p", sp.simplify(f.subs(r, p) - p) == 0)
    # min(P,R) ≤ F ≤ max(P,R): test F - min ≥ 0 and max - F ≥ 0 on a grid in [0,1]²
    pts = [(sp.Rational(a, 10), sp.Rational(b, 10)) for a in range(1, 11) for b in range(1, 11)]
    lower = all((2 * pv * rv / (pv + rv)) >= min(pv, rv) for pv, rv in pts)
    upper = all((2 * pv * rv / (pv + rv)) <= max(pv, rv) for pv, rv in pts)
    check("P3 min(P,R) ≤ F", lower)
    check("P3 F ≤ max(P,R) (so F ∈ [0,1])", upper)
    # harmonic ≤ arithmetic mean (AM-HM inequality) — sanity on the aggregation
    check("P3 F ≤ (P+R)/2", all((2 * pv * rv / (pv + rv)) <= (pv + rv) / 2 for pv, rv in pts))


# ---- P4 — DTW-decay similarity is in [0,1] (cost ≥ 0 ⇒ 1-cost/(m+n) ≤ 1; max(0,·) ⇒ ≥ 0) -------
def p4_dtw() -> None:
    s, lam, delta = sp.symbols("s lambda delta", nonnegative=True)
    d = (1 - s) * (1 + lam * delta)  # per-step cost in analysis/vertex.py:_dtw_decay
    # per-step cost is nonnegative for s∈[0,1], λ,δ≥0
    grid = [(sp.Rational(a, 4), sp.Rational(b, 4), sp.Rational(c, 4))
            for a in range(5) for b in range(5) for c in range(5)]
    check("P4 per-step cost ≥ 0", all(d.subs({s: sv, lam: lv, delta: dv}) >= 0
                                      for sv, lv, dv in grid))
    cost, m, n = sp.symbols("cost m n", positive=True)
    D = 1 - cost / (m + n)
    check("P4 D ≤ 1 when cost ≥ 0", sp.simplify((1 - D)) == sp.simplify(cost / (m + n)))  # 1-D = cost/(m+n) ≥ 0
    # max(0, D) ∈ [0,1]: upper bound from cost≥0, lower from the clamp
    check("P4 clamp gives ≥ 0", sp.Max(0, sp.Rational(-3)) == 0 and sp.Max(0, sp.Rational(1, 2)) == sp.Rational(1, 2))


# ---- P5 — pass@k estimator equals 1 - P(zero successes in k draws), bounded, monotone ----------
def p5_passk() -> None:
    def passk(n, c, k):
        return 1 - sp.binomial(n - c, k) / sp.binomial(n, k)

    # combinatorial identity: P(zero of c successes appear in a k-subset) = C(n-c,k)/C(n,k)
    for n, c, k in [(5, 2, 3), (8, 3, 4), (6, 6, 2), (7, 0, 3)]:
        all_subsets = list(combinations(range(n), k))
        succ = set(range(c))  # the c "passing" samples
        zero = sum(1 for sub in all_subsets if not (set(sub) & succ))
        brute = 1 - sp.Rational(zero, len(all_subsets))
        check(f"P5 pass@k identity n={n},c={c},k={k}", sp.simplify(passk(n, c, k) - brute) == 0)
    # bounds + monotonicity in k
    check("P5 pass@k=0 when c=0", passk(7, 0, 3) == 0)
    check("P5 pass@k=1 when c=n", passk(5, 5, 2) == 1)
    check("P5 pass@k nondecreasing in k", passk(10, 3, 4) >= passk(10, 3, 2))


# ---- P6 — Wilson bounds are exactly the roots of the score equation (p̂-p)² = z² p(1-p)/n -------
def p6_wilson() -> None:
    phat, z, n, p = sp.symbols("phat z n p", positive=True)
    score_eq = (phat - p) ** 2 - z**2 * p * (1 - p) / n  # = 0 at the interval bounds (score test inversion)
    center = (phat + z**2 / (2 * n)) / (1 + z**2 / n)
    half = (z / (1 + z**2 / n)) * sp.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))
    # each Wilson bound is a root of the score equation (substitute -> simplifies to 0)
    for sign, name in ((-1, "lower"), (1, "upper")):
        residual = sp.simplify(score_eq.subs(p, center + sign * half))
        check(f"P6 Wilson {name} bound solves the score equation", residual == 0)
    # and the score equation has exactly these two roots
    roots = set(sp.solve(sp.Eq(score_eq, 0), p))
    check("P6 score equation has exactly 2 roots", len(roots) == 2)


# ---- P7 — one finite prerequisite lattice, not a proof about the stochastic runtime -----------
def p7_fixedpoint() -> None:
    R = frozenset({"r1", "r2", "r3", "r4"})  # a requirement set
    universe = [frozenset(c) for k in range(len(R) + 1) for c in combinations(sorted(R), k)]

    # This example's fixed prerequisites make Φ monotone and inflationary; ledger append-only
    # storage alone would establish neither state sufficiency nor monotone validation.
    prereq = {"r1": frozenset(), "r2": {"r1"}, "r3": {"r1"}, "r4": {"r2", "r3"}}

    def Phi(S):
        return frozenset(S | {r for r, pre in prereq.items() if set(pre) <= set(S)})

    inflationary = all(S <= Phi(S) for S in universe)
    monotone = all((S <= T) <= (Phi(S) <= Phi(T)) for S in universe for T in universe)
    check("P7 Φ inflationary (S ⊆ Φ(S))", inflationary)
    check("P7 Φ monotone", monotone)

    # Kleene iteration from ∅ — a non-decreasing chain bounded by R must stabilize
    chain, S = [], frozenset()
    while True:
        chain.append(S)
        nxt = Phi(S)
        if nxt == S:
            break
        S = nxt
    lfp = chain[-1]
    steps = len(chain) - 1  # strict increases; len(chain) includes the final equality evaluation
    check("P7 chain non-decreasing", all(chain[i] <= chain[i + 1] for i in range(len(chain) - 1)))
    check("P7 reaches a fixed point", Phi(lfp) == lfp)
    check("P7 example reaches lfp in ≤ |R| strict increases", steps <= len(R))
    check("P7 lfp is least fixed point", lfp == min((S for S in universe if Phi(S) == S), key=len))
    # Oracle-relative coverage in this example, not semantic correctness of a live artifact.
    R_required = R
    check("P7 example required-set coverage ⇔ lfp = R", (lfp >= R_required) == (lfp == R))
    # Each repeated full sweep is fair: every requirement is reconsidered on every sweep.
    def Phi_perm(S, order):
        cur = set(S)
        for r in order:
            if set(prereq[r]) <= cur:
                cur.add(r)
        return frozenset(cur)
    fps = set()
    for order in permutations(sorted(R)):  # all repeated full-sweep orders for this example
        S = frozenset()
        while (nxt := Phi_perm(S, order)) != S:
            S = nxt
        fps.add(S)
    check("P7 example fair full sweeps reach the same lfp", fps == {lfp})


# ---- P8 — conditional hitting-time bound: geometric identity and one exact finite chain -------
def p8_completion_time() -> None:
    epsilon, wait = sp.symbols("epsilon wait", positive=True)
    # For 0 < epsilon <= 1, waiting for a strict increase solves E = 1 + (1-epsilon) E.
    geometric_mean = sp.solve(sp.Eq(wait, 1 + (1 - epsilon) * wait), wait)[0]
    check("P8 geometric waiting mean = 1/epsilon", sp.simplify(geometric_mean - 1 / epsilon) == 0)
    # Prefix states contain 0, 1, 2, or 3 credits; 3 is absorbing. Each other state adds
    # exactly one credit with probability 2/5. (I-Q)^-1 1 gives exact expected hitting times.
    progress = sp.Rational(2, 5)
    transient = sp.Matrix([[1 - progress, progress, 0],
                           [0, 1 - progress, progress],
                           [0, 0, 1 - progress]])
    expected = (sp.eye(3) - transient).inv() * sp.ones(3, 1)
    check("P8 finite chain attains (|R|-|S0|)/epsilon",
          all(expected[s0] == (3 - s0) / progress for s0 in range(3)))


def main() -> int:
    for fn in (p1_normalization, p2_composite, p3_fscore, p4_dtw, p5_passk, p6_wilson,
               p7_fixedpoint, p8_completion_time):
        fn()
    width = max(len(name) for name, _ in CHECKS)
    for name, ok in CHECKS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}")
    failed = [name for name, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} symbolic checks passed.")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
