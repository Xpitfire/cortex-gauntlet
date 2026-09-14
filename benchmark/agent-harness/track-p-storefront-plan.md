# Track P — "Project": one-prompt full-repo generative build + evaluation

Status: **P0 + P3 landed (mock end-to-end); P1/P4 structural** — see "Implementation status" below.
Builds on Track G (generative). The goal is a single,
open-ended natural-language prompt that asks a harness to build an entire production-shaped web
application repository (a Zalando-style storefront), then evaluate the result rigorously across
quantitative *and* qualitative axes, executed in a safe sandbox.

This document is the requirements + goals + milestones the implementation follows. It complements
the user's brief with researched gaps (VERTEX, LLM-judge methods, sandboxing).

---

## 0. Why a new track

Track G (`generative`) builds a *single-file* app from a tight brief and measures it with a
build→e2e→visual→plan composite. The new task is categorically harder:

- **Open-ended**: the prompt gives an NLP direction + acceptance intent + reference screenshots, and
  deliberately does **not** prescribe the repo structure, stack, or file layout. The harness decides
  architecture — and that decision is itself part of what we score.
- **Full-repo**: backend (catalog/cart/checkout/orders), frontend (PWA), tests, infra/CI, a payment
  demo (Stripe test mode), state, routing, accessibility, responsive design.
- **Long-horizon + multi-file**: dozens of files, cross-module contracts, a real build.
- **Aesthetic**: the look-and-feel vs. the reference screenshots matters, not just functionality.

So it gets its own track, **P (Project)** — codename *Atelier* — reusing Track G plumbing where
possible (briefs, harnesses, the report shell, the TUI), with a new sandboxed runner + scorer.

---

## 1. The open prompt (Goal A)

A single brief, `suites/generative/fixtures/storefront/` with:
- `BRIEF.md` — the natural-language prompt (direction + requirements + explicit "you choose the
  structure/stack" + reference to screenshots).
- `screenshots/01-home.png … 05-cart.png` — the 5 reference frames (home, mega-nav, listing, PDP,
  cart) saved from the user.
- `acceptance.json` — the hidden acceptance spec (NOT shown to the harness): user journeys, REST
  contracts, must-have features, a11y/PWA checks, and the visual rubric anchors.

### Prompt principles
- **Direction, not blueprint.** Describe *what the product is and must do*, name the domain
  (fashion e-commerce storefront), point at the screenshots as the visual/UX target, and list
  capability requirements as outcomes ("a shopper can browse categories, open a product, pick a
  size, add to cart, and check out with a test payment"). Do **not** dictate folders, frameworks,
  or file names — architecture is the harness's job and a scored signal.
- **Bounded scope, real depth.** Seed catalog data is allowed (provide a small product JSON);
  payments are **Stripe test-mode / demo** only (no real charges); auth can be a stub.
- **Self-contained + runnable.** One documented command builds and serves it; it must run in the
  sandbox with no external network beyond allowed test endpoints.

### Required capabilities (outcomes the harness must deliver)
Catalog browse + category nav (mega-menu), search/filter, product detail (PDP) with variant/size
select, cart (add/update/remove, totals, tax/shipping), checkout flow, **Stripe test-mode payment**,
order confirmation, responsive layout, **PWA** (installable, offline shell, service worker),
basic accessibility (landmarks, alt text, keyboard nav), automated tests, and a build/CI manifest.

---

## 2. Evaluation & scoring (Goal B)

We score every run on a **vector of signals**, then combine into a calibrated composite. Signals
split into **objective/quantitative** (executed, deterministic) and **qualitative** (judged), and we
never let a judge override a hard objective failure.

### 2.1 Objective signals (sandbox-executed, deterministic)
- **Build gate** — does it install + build + boot in the sandbox? (0/1, hard gate).
- **Functional completeness** — per-feature e2e via Playwright + black-box REST against the running
  app, scored against `acceptance.json` user journeys (browse→PDP→cart→checkout→pay→confirm).
- **PWA/a11y** — Lighthouse-style checks (manifest, service worker, installability) + axe-core a11y
  violations (count, severity-weighted).
- **Code/static health** — multi-file static analysis (ruff/eslint/semgrep as available), test
  presence + the harness's own tests passing, dependency/slopsquat scan, secret scan.
- **Robustness** — does it survive basic fuzz (bad inputs, empty cart, invalid card) without 500s.

### 2.2 Structural/trajectory similarity
Published trajectory evaluation (arXiv:2402.00854) embeds the nodes of a *relational trajectory* (computational
graph) and scores the **cross-similarity** between candidate embeddings and a **reference
distribution**, aligned with DTW + cosine and a linear distance-decay — sensitive to incremental
quality *independent of completion*. Here the scorer works over a repo build rather than a sampled
node graph — cheaper and equally robust:

- **Capability trajectory.** Represent the candidate as an *ordered capability/route trajectory*
  (e.g. `home → category → search → pdp → cart → checkout → payment → order`), recovered from the
  routes/e2e it actually serves. Embed each step's natural-language descriptor + observed behaviour
  with a sentence-embedding model.
- **Reference distribution.** The acceptance spec defines a reference set of capability descriptors
  (and, optionally, embeddings sampled from K reference implementations). 
- **Cross-similarity, two forms:**
  - **Unordered (BERTScore-style):** cosine cross-similarity matrix `S` between candidate steps and
    reference steps; score = ½(mean_i max_j S_ij + mean_j max_i S_ij) — bidirectional soft match,
    cheap, order-free. (Captures "which capabilities are present and how well".)
  - **Ordered (VERTEX-DTW):** DTW-align the candidate trajectory to the reference using cosine
    distance with a **linear distance-decay** penalty for far-apart alignments — rewards building the
    journey in a coherent order (cross-similarity kernel over the ordered journey).
- **Baseline normalization.** Subtract an expected-random-match baseline (cosine of shuffled/random
  descriptors) and clamp to [0,1], so the score reflects signal above chance.
- **Architecture trajectory (bonus).** Embed the file/module tree (layered: api/domain/ui/tests) and
  cross-score against an "idealized layered architecture" descriptor set — rewards clean separation
  without prescribing exact names.

This gives a **continuous, completion-independent** quality signal that credits partial, well-formed
builds and is robust to different-but-valid structures — the key requirement for an open prompt.

### 2.3 Qualitative judges (LLM, bias-controlled)
Grounded in current LLM-judge practice (G-Eval rubric form-filling, Prometheus rubric-trained
judges, MT-Bench pairwise, RubricEval reasoning, calibration + position-bias mitigation):
- **Visual/aesthetic fidelity** — a **vision LLM** compares the candidate's rendered screenshots
  (captured in-sandbox by Playwright) to the reference frames on an explicit rubric (layout,
  hierarchy, color/brand, component fidelity, polish). Pointwise rubric score + reasoning.
- **Code-quality & architecture** — a rubric LLM judge over the repo (modularity, encapsulation,
  typing, separation of concerns, idiomatic stack use), G-Eval-style decomposed criteria.
- **UX/journey coherence** — judge the captured journey (screens + transitions) for task flow.

**Bias + reliability controls (must-haves):**
- **Rubric-anchored, decomposed** scoring with required reasoning (reduces variance — RubricEval).
- **Position/verbosity bias**: for any pairwise use, **swap order and average**; prefer pointwise +
  fixed anchors for absolute scores.
- **Self-consistency**: N samples per judge, report median + dispersion; low-agreement cells flagged.
- **Calibration & cross-check**: judges are **gated by objective signals** — a high aesthetic score
  on an app that didn't build is invalid; report judge–objective agreement and confidence intervals.
- **Provenance**: store every judge prompt, rubric, raw verdict, and the screenshots judged.

### 2.4 Composite
A weighted, gated composite: `Build` gate × (w1·Functional + w2·VERTEX + w3·PWA/a11y + w4·Visual +
w5·CodeArch + w6·Robustness), weights in the run config, every sub-score persisted to the
`runrecord.json`, with CIs. The report shows the full vector, not just the scalar — so Cortex's
value (Synapse driving more requirements to completion over the long horizon) is visible per-signal.

---

## 3. Sandboxed containerized execution (Goal C)

Untrusted, model-generated full-stack apps **must not run on the host**. A new sandbox runner:

- **Docker isolation.** Each candidate runs in an ephemeral container: pinned base image, the
  generated repo mounted read-only → copied into a work dir, non-root user, **no host mounts**.
- **Resource limits.** CPU/memory/pids/disk caps, wall-clock timeouts per phase (install/build/serve),
  output size caps; container killed + removed on completion or timeout.
- **Network policy.** Default **deny-egress**; an allowlist only for the package registry during a
  separate install phase and the Stripe **test** endpoint; the serve+test phase runs on an internal
  network with no egress. (Mirrors Cortex's governed-sandbox posture; reuse `cortex docker`/policy
  patterns where possible rather than raw daemon access.)
- **Browser-in-sandbox.** Playwright (chromium) runs **inside** the sandbox network against the
  app's bound 127.0.0.1 port, captures screenshots + traces + console/network logs as evidence.
- **Tool usage.** The build phase may use a constrained toolchain (package manager, compiler, test
  runner) inside the container; everything is capture-only and policy-gated.
- **Runner contract.** A `SandboxResult` (built, served, e2e checks, screenshots, lighthouse/axe,
  logs, exit info) → mapped into the Track-P result the scorer + report consume. Graceful, isolated
  failure (a crash is data, never aborts the suite — consistent with the TUI runner).
- **Degradation.** If Docker is unavailable, the track reports `skip` with a clear reason (like the
  TS/JS-without-node path) — never a fake pass.

---

## 4. Goals checklist (acceptance for this track)

- [ ] G-A1 `BRIEF.md` open prompt authored (direction + outcomes + screenshot refs, no blueprint).
- [ ] G-A2 5 reference screenshots saved under the fixture; referenced from the brief.
- [ ] G-A3 `acceptance.json` hidden spec (journeys, REST contracts, PWA/a11y checks, visual anchors).
- [ ] G-A4 Small seed catalog dataset provided to the harness.
- [ ] G-B1 Objective signal runners (functional e2e, PWA/a11y, static/health, robustness).
- [ ] G-B2 trajectory similarity scorer (unordered cross-sim + ordered DTW-decay + baseline norm).
- [ ] G-B3 Vision-LLM aesthetic judge vs reference frames (rubric, self-consistency).
- [ ] G-B4 Code/architecture + UX rubric judges with swap/calibration/bias controls.
- [ ] G-B5 Gated, weighted composite; every sub-score + CI in the runrecord; report renders the vector.
- [ ] G-C1 Docker sandbox runner (isolation, limits, deny-egress + allowlist, non-root, ephemeral).
- [ ] G-C2 Browser-in-sandbox capture (Playwright screenshots/traces/logs as evidence).
- [ ] G-C3 Runner contract + Track-P wiring into the suite, report, and TUI; Docker-absent → skip.
- [ ] G-D1 Report + TUI surface the full signal vector, screenshots side-by-side vs references.
- [ ] G-D2 Honest methodology notes; judge–objective agreement + CIs shown.

---

## 5. Phased milestones (proposed build order)

1. **P0 — Scaffolding & prompt.** Track-P brief + screenshots + acceptance spec + seed data; wire a
   `--track project` that (initially) runs mock so the plumbing/report/TUI exist end-to-end.
2. **P1 — Sandbox runner.** Docker isolation + resource/network policy + Playwright-in-sandbox +
   `SandboxResult`; validate on a hand-written reference repo.
3. **P2 — Objective scorers.** Functional e2e/journeys, PWA/a11y, static/health, robustness.
4. **P3 — VERTEX scorer.** Embedding-based unordered + ordered DTW-decay cross-similarity + baseline.
5. **P4 — LLM judges.** Vision aesthetic + code/arch + UX rubric judges with bias controls + calibration.
6. **P5 — Composite + report + TUI.** Gated weighted composite, CIs, full-vector report + IDE viewer.
7. **P6 — Live validation.** Run a real harness (codex/cortex) live in the sandbox on the brief;
   report the signal vector; tune weights; document honestly.

---

## 6. Researched gaps complemented (beyond the user's brief)

- **Judge validity is undertested** (2025–26 literature) → we *gate judges by objective signals*,
  report judge–objective agreement + CIs, and use self-consistency + swap-and-average, rather than
  trusting a single LLM verdict.
- **Visual eval needs grounding** → vision judge scores against the *captured* in-sandbox screenshots
  (real render), with an explicit anchored rubric, not a vibe rating.
- **Open-prompt fairness** → no blueprint in the prompt; structure is scored via VERTEX similarity to
  an *idealized* descriptor set + an architecture rubric, so different-but-valid layouts aren't
  penalized.
- **Security** → generated full-stack code is untrusted; deny-egress sandbox + non-root + ephemeral
  containers + capture-only, consistent with Cortex governance.
- **Reproducibility** → pinned images, seeded data, fixed embedding model, persisted judge prompts +
  evidence, multi-seed with CIs.

## Implementation status (what's built)

- ✅ **P0 scaffold + prompt + mock + plumbing.** `Track.PROJECT`; fixture (`BRIEF.md`, 5 screenshots,
  `acceptance.json`, `catalog.json`); `gauntlet/project/` (models, corpus, mock, score, judge,
  sandbox, run); `gauntlet run --track project` and `gauntlet tui --track project` run mock
  end-to-end → `runrecord.json` + `report.html` (+ screenshot gallery) + TUI viewer + `--load`;
  wired into the site. seeds=1.
- ✅ **P3 VERTEX scorer** (`analysis/vertex.py`): efficient realization — sentence-transformers
  (`all-MiniLM-L6-v2`, env-selectable via `GAUNTLET_VERTEX_MODEL`) or a deterministic hashing
  fallback; cosine cross-similarity, unordered F + ordered DTW-with-distance-decay, chance-baseline
  normalization; capability + architecture trajectories. Unit-tested.
- ✅ **P5 (partial) composite + report + TUI**: gated weighted `SignalVector`, the project report
  renders the full vector + reference frames, the TUI shows it; per-signal Cortex delta surfaced.
- ✅ **P1/P2 sandbox + in-container probe** (`project/sandbox.py`, `project/probe.py`, `launch.py`,
  `sandbox/Dockerfile`): two-phase Docker flow — build a per-run image FROM the base (Node 22 + pnpm +
  Python + Playwright + the probe) that COPYs the repo and runs install+build (registry egress), then
  `docker run` the probe with **`--network none`, non-root, `--cap-drop ALL`, no-new-privileges,
  CPU/mem/pid/time limits, ephemeral**. The probe discovers the launch plan, serves the app on
  127.0.0.1, runs the acceptance journeys (REST discovery + Playwright UI heuristics), PWA/a11y, and
  robustness, captures screenshots, writes `result.json` → mapped to a `Candidate` (behaviour-derived
  capability trajectory). `docker_available()` gate → `skip` when Docker is absent.
  **Validated**: launch discovery (6), probe HTTP journeys vs an in-process stub (4), and the sandbox
  pure helpers — Dockerfile/run-argv hardening + result→Candidate (4) — are unit-tested without Docker;
  the Docker/browser orchestration runs in a Docker-enabled env.
- ✅ **P4 judges** (`project/judge.py`): three EXPLICIT backends chosen via `--vision-judge`, with the
  backend that actually ran recorded on every result (never silently swapped): `heuristic` (deterministic
  proxy, offline/mock), `clip` (local CLIP VLM — image-image cosine, no API), `claude-vision` (rubric LLM
  via `claude -p`, raises if the CLI is absent). `clip`/`claude-vision` require `--live`; all gated on serving.
- ⏳ **P6**: a live validation run (real harness → sandbox → judges) once Docker + the sandbox image
  are provisioned; tune weights; add a Stripe-test egress allowlist proxy so the payment journey can
  pass under the otherwise no-egress serve phase.

### Recent extensions (post-P6, validated live)
- ✅ **VERTEX-architecture** now derives **role-level descriptors** from the repo (backend API / UI /
  domain-service / data-models / tests / env-config) instead of bare directory names — lifted arch
  similarity from ~0.22 to ~0.78 on the storefront candidate (`project/arch.py`).
- ✅ **Reference-free VERTEX-QE** (`project/vertexqe.py`, `--vertex-ref auto|brief|repo|qe|consensus`):
  brief-extracted + reference-repo-prior + leave-one-out consensus references, validated by rank-
  correlation against the authored reference (`project/validate_vertexqe.py`; paper §5.1.1). Live/rescore
  `auto` uses QE; mock `auto` keeps authored fixtures stable.
- ✅ **`--vision-judge auto`** (new default) → CLIP under `--live`, heuristic for mock; the configured
  judge/embedding model is used or fails loudly (no silent swap to a surrogate).
- ✅ **JS/TS code quality** (eslint + tsc) folded into `code_arch` alongside ruff/mypy
  (`analysis/lint_types.py`; pinned toolchain in `benchmark/package.json`).
- ✅ **Cortex-over-X ≥ raw X**: Synapse arms best-of their plan→repair passes by *real composite* (each
  sandboxed) and merge repairs non-destructively, so marker-chasing can't regress functionality.
- ✅ **Per-signal resilience**: a transient fork/exec fd-race degrades one signal (excluded from the
  renormalized composite), never a blanket zero.
- ✅ **Re-scoring** any track from persisted artifacts with no re-generation
  (`gauntlet rescore <run> [--tracks all] [--vision-judge …]`; `rescore_tracks.py`).

Mock result today shows the intended signal: Cortex composite **+43 pts** vs raw on the long-horizon
build (VERTEX +30, functional +73) — the differentiation single-shot tasks couldn't produce.

## 7. Open decisions for the user (resolved)
- Embedding model: **local sentence-transformers `all-MiniLM-L6-v2`** (deterministic hashing fallback).
- Vision judge: **Claude vision via the harness**.
- Track: **own Track P**, **seeds=1** (full-repo builds are costly, esp. live with Cortex+Synapse).
- Sandbox toolchain: **Node/pnpm + Python**, **React + Vite** (also exercises harness guardrails /
  software-governance / policy compliance during the install phase).

## 7b. Remaining open decisions
- Embedding model for VERTEX (local sentence-transformers vs. a hosted embedding API).
- Vision-judge model (Claude vision via the harness vs. a fixed judge model) and cost ceiling.
- Whether Track P is its own track or a "complex" tier of Track G.
- Sandbox base image + allowed toolchains (Node/pnpm + Python? which frameworks permitted, if any).
