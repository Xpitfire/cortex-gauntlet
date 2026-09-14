# Track P — scoring & measurement spec

Concrete realization of the Track-P scorer (Goal B). Every run yields a **signal vector**, combined
into a gated composite. Objective signals are executed/deterministic; the VERTEX-style similarity is
embedding-based; qualitative signals are LLM judges with bias controls. All sub-scores + CIs persist
to `runrecord.json`; nothing lets a judge override a hard objective failure.

## A. Signal vector (each normalized to [0,1] unless noted)

| Signal | Type | Source |
| --- | --- | --- |
| `build` | gate {0,1} | sandbox install+build+boot |
| `functional` | objective | Playwright journeys vs `acceptance.json` (behaviour-anchored: checks assert structure/state — a reached checkout route/payment form, a real cart line item — not incidental keyword text; a stateful flow the offline sandbox cannot drive is reported `evaluable:false` and **excluded** from the functional denominator, not hard-failed). The REST-contract walk feeds the behaviour-derived VERTEX capability trajectory, not this signal |
| `pwa_a11y` | objective | manifest/service-worker/installable + axe-core + responsive |
| `code_health` | objective | multi-lang static (eslint/ruff/semgrep), tests present+green, deps, secrets |
| `robustness` | objective | empty cart / bad card / unknown route → no 500/stacktrace |
| `security` | objective | Semgrep (security-audit + secrets) / Bandit over the repo → CWE-weighted |
| `vertex` | similarity | capability + architecture trajectory cross-similarity (below) |
| `visual` | judge | vision judge vs reference screenshots — `auto`→CLIP under --live, or claude-vision |
| `code_arch` | judge | layering + lint/type cleanliness (ruff+mypy / eslint+tsc), folded into the judge |
| `ux` | judge | journey coherence over captured screens (CLIP image space) |

## B. VERTEX realization (efficient, completion-independent)

Published trajectory evaluation (arXiv:2402.00854) embeds nodes of a relational trajectory and scores
cross-similarity of candidate embeddings against a **reference distribution**, DTW-aligned with cosine
and a linear distance-decay; it is sensitive to incremental quality regardless of final success.
Here the reference distribution is the **acceptance descriptor set** (optionally augmented by K
reference-implementation embeddings), which avoids per-node graph sampling.

Let `φ(·)` be a fixed sentence-embedding model returning unit vectors. The candidate is reduced to a
**capability trajectory** `C = (c_1..c_m)` — short NL descriptors of the capabilities it actually
serves, recovered from its routes + which journeys passed (so it reflects *behaviour*, not claims).
The reference is `R = (r_1..r_n)` = `capability_descriptors` from `acceptance.json`.

Cross-similarity matrix: `S_ij = cos(φ(c_i), φ(r_j))`, `S ∈ [-1,1]^{m×n}`.

1. **Unordered soft match (BERTScore-style):**
   - precision `P = mean_i max_j S_ij`, recall `Rc = mean_j max_i S_ij`
   - `F = 2·P·Rc / (P + Rc)`  (recall-weighted so missing capabilities hurt)

2. **Ordered match (DTW with positional decay):**
   - cost `d(i,j) = (1 − S_ij) · (1 + λ·|i/m − j/n|)`  (cosine distance × linear distance-decay, `λ≈0.5`)
   - DTW finds the min-cost monotonic alignment path of length `L`; `ord = 1 − (DTW_cost / L)`

3. **Baseline normalization (signal above chance):** compute `F`/`ord` for `B` shuffled/random
   descriptor sets → expected-random `b₀`; `x* = clamp((x − b₀)/(1 − b₀), 0, 1)` for each.

4. **Combine:** `vertex = α·F* + (1−α)·ord*`, `α≈0.6`. An **architecture-trajectory** variant runs the
   same kernel over **role-level architecture descriptors** derived from the repo (backend API / UI /
   domain-service / data-models / tests / env-config — each emitted only on real evidence, not bare
   directory names) vs `architecture_anchors` → `vertex_arch`; the reported
   `vertex = 0.7·vertex_capability + 0.3·vertex_arch`.

Cost: one embedding pass + `O(mn)` similarity + `O(mn)` DTW — cheap, deterministic, reproducible
(pin the embedding model). It credits partial, well-formed, differently-structured builds — exactly
what an open prompt needs — and is robust to ordering/length. The **configured** embedding model is
used or the run fails loudly — never a silent swap to a different method.

**Reference-free VERTEX (VERTEX-QE), configured by `--vertex-ref`:** the reference `R` need not be
hand-authored. `brief` extracts it from the public brief (capability) + role descriptors (architecture);
`repo` scores architecture *typicality* against a curated reference-repo prior; `consensus` adds
leave-one-out peer agreement across the arm pool (MBR); `qe` aggregates them. `--vertex-ref auto`
resolves to `qe` for live Project/rescore runs and to `authored` for offline mock fixtures. Use an
explicit `--vertex-ref authored|brief|repo|qe|consensus` to force a mode. The legacy
`GAUNTLET_VERTEX_REF` env var remains only as a low-level helper fallback. See
section 5.1.1 of the docs paper (`gauntlet/docs.py`).

## C. LLM judges (bias-controlled)

Grounded in current practice (G-Eval decomposed form-filling; Prometheus rubric judges; MT-Bench
position/verbosity bias; RubricEval reasoning reduces variance; calibration + CIs; judge-validity
caution):

- **Pointwise, rubric-anchored, decomposed.** Each judge scores explicit criteria 0–4 with required
  reasoning, then we normalize to [0,1]. Rubrics live in `acceptance.json` (`visual_anchors`) + the
  code/UX rubric files.
- **Vision aesthetic judge.** Input = the candidate's **in-sandbox** rendered screenshot for a screen
  + the reference frame + that screen's rubric; output = per-criterion scores + rationale. Real render
  only — never a vibe rating of code.
- **Self-consistency.** `N=3` samples/judge; report **median + IQR**; flag low-agreement cells.
- **Position/verbosity bias.** Absolute scores are pointwise with fixed anchors. Any pairwise
  harness comparison is run **both orderings and averaged**; verbosity controlled by rubric anchoring.
- **Calibration & cross-check.** Judges are **gated by objective signals**: `visual`/`ux` scores are
  voided unless the app built *and served* (they read renders); the static `code_arch` judge needs
  only a built repo with scoreable files (it reads code, not the running app) and is voided on a
  failed build. We persist per-run judge↔objective
  agreement (Spearman) and bootstrap CIs over (criteria × samples). Disagreement is surfaced, not hidden.
- **Provenance.** Every judge call stores its prompt, rubric, raw verdict, model id, and the exact
  screenshots/files judged.

## D. Composite

```
build ∈ {0,1}                       # hard gate
quality = Σ_k w_k · s_k             # weights sum to 1 (renormalized over surviving signals on degrade)
score   = build · quality
```
Weights (sum to 1, in run config): `functional 0.26 · vertex 0.14 · visual 0.16 · code_arch 0.12 ·
pwa_a11y 0.09 · security 0.09 · robustness 0.08 · code_health 0.06`. Multi-seed where affordable → mean ±
bootstrap CI. The report renders the **full vector** (radar + per-signal bars + side-by-side screenshots
vs references), so the Cortex+Synapse advantage is visible per-signal — and a high judge score on a
broken build is impossible by construction.

- **Per-signal resilience.** A transient infra hiccup in one analyzer/judge (e.g. the threaded fork/exec
  fd-race under a busy suite) degrades ONLY that signal — recorded in `detail.degraded` and **excluded
  from the renormalized composite** — never a blanket-zero of the whole cell. A genuine (non-transient)
  error still surfaces.
- **Best-of-passes (Cortex never worse than raw).** The Synapse-wrapped arm plans → repairs over several
  passes; the **highest-composite** sandboxed pass ships, and repairs merge non-destructively. Docker-cost
  bound: with >2 snapshots only the floor (pass 1 ≈ the raw single-shot) and the final cumulative pass
  are sandboxed (middle passes are skipped); each repair iteration is sandboxed as it lands. A
  marker-chasing repair can't regress the shipped score below the floor pass.

## E. Anti-gaming / validity guards
- Behaviour-derived capability trajectory (passed journeys), not the harness's self-claims.
- Hidden acceptance spec; visual rubric anchored to real renders.
- Judges gated by + cross-checked against objective signals; CIs + agreement reported.
- Pinned embedding + judge models — used as configured or fail loudly, no silent fallback to a surrogate.
- Synapse arms best-of by *real composite* (not spec-marker presence), so "push for completeness" can't
  trade functional regressions for marker wins. Seeds; persisted evidence → reproducible, auditable.
