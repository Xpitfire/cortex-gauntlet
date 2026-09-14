# Implementation Plan

Phased roadmap. **Phase 1 (M0) is this deliverable** — requirements, architecture, plans,
base structure. Later milestones are sequenced to land a thin vertical slice early
(one track, one adapter, one report) before broadening.

## M0 — Foundations & design ✅ (this deliverable)

- [x] SOTA research synthesis with citations (`research-state-of-art.md`).
- [x] Requirements, architecture, security model, acceptance checklist.
- [x] Attack taxonomy, dimensions, scoring/judging, reporting, reuse-map docs.
- [x] Base directory skeleton (`suites/`, `adapters/`, `schemas/`, `results/`).
- [ ] Confirm naming (`benchmark/` + Gauntlet/Sentinel/Forge/Auditor) and language scope.

## M1 — Vertical slice: Track S text-only, 2 adapters, 1 report ✅ (landed)

Implemented in `benchmark/gauntlet/` (pure stdlib, zero-dep) + `suites/security/` +
`benchmark/tests/`. Verified: 16 unit tests pass, `ruff` clean, end-to-end smoke writes a
valid RunRecord + a ~66 KB interactive HTML report; containment `payloads_executed=0`;
harness delta raw 26.7% vs Cortex-wrapped 6.7% ASR (+20.0 pts).

- [x] Minimal **Inspect-compatible** Task/Solver/Scorer core (`adapters/base.py`, `scoring/`,
  `run.py`). *Deviation:* own zero-dep core instead of a hard Inspect AI dependency; a thin
  Inspect adapter is deferred so the slice runs anywhere.
- [x] Typed data contract Case/Transcript/Score/RunRecord (`models.py`, `enums.py`) →
  RunRecord JSON; `schemas/README.md` documents it. *Deferred:* formal JSON-Schema files +
  `jsonschema` validation (dataclasses enforce the shape at construction today).
- [x] Three offline **mock** adapters (raw Codex, **OpenCode** OSS, Cortex-wrapped) + real
  CLI adapters for **`cortex agent ask`** and **`opencode run`** (shared `SubprocessCliAdapter`
  base). *Deviation:* live CLI adapters are best-effort, untested against a live CLI here.
- [x] **Logical** capture-only sandbox: canary/honeypot registry + structural danger patterns
  (`sandbox.py`). *Deferred to M2:* Docker materialization (only L1 side-effect replay needs
  it; M1 executes nothing regardless).
- [x] Track S scorers: **L0** canary+structural (`scoring/l0.py`) fused into **L2** judge
  rubric — `HeuristicJudge` (offline default) + `CortexJudge` (`cortex agent ask`).
- [x] 20 cases: 3 harmful objectives × 5 techniques + 2 canary probes + 3 benign
  over-refusal controls (`suites/security/`).
- [x] Report **v0**: Artificial-Analysis-styled self-contained HTML (ECharts highlights cards,
  ASR-by-harness with Wilson-CI tooltip, ASR-by-technique, over-refusal, filterable case
  explorer with drill-down, CSV + print/PDF). *Deviation:* Python generator + CDN ECharts;
  the Vite+React+vendored-ECharts single-file build is M7.
- [x] One end-to-end smoke run → `results/<run-id>/{runrecord.json, report.html}`.

## M2 — Track S breadth + multimodal ✅ (landed)

Verified: 30 tests pass, `ruff` clean, smoke (65 cases incl. held-out × 3 harnesses = 195
results) writes runrecord + report + 6 multimodal assets; containment `payloads_executed=0`.
3-way separation raw 25.0% → OpenCode 16.7% → Cortex-wrapped 1.7% ASR; indirect ASR (33%) >
direct (23%); image modality gap 66.7% vs 16.7% text.

- [x] Full surface coverage: `repo_file`, `tool_output`, `memory_session` envelopes
  (`surfaces.py`); mock susceptibility scales by surface; ASR-by-surface in the report.
- [x] Obfuscation generators — 13 techniques incl. leetspeak, payload-split, zero-width,
  many-shot, low-resource, past-tense, ASCII-art, cipher (`transforms.py`), with round-trip tests.
- [x] Multimodal: single text seed → **image (FigStep-style SVG)** + **audio (stdlib WAV)**
  variants (`modality.py`), rendered into the run dir and shown in the case explorer.
  *Deferred:* raster PNG via Pillow and real OCR/TTS engines.
- [x] **L1 logical side-effect scorer** — in-memory `MockEnvironment` replays captured actions
  for exfil/destructive-git/malicious-install/remote-exec (`sandbox.py`, `scoring/l1.py`); fused
  into the judge (SANDBOX > DETERMINISTIC > JUDGE). *Deferred:* Docker container materialization.
- [x] Utility-under-attack metric (indirect cases carry a benign task) + over-refusal; both in
  the report (utility chart + confirmed-vs-judge-only hatched chart).
- [x] Held-out split flag (`--held-out`, excluded by default). *Deferred:* vendoring real
  external datasets (needs license review) — scaffold + `PROVENANCE.md` per `docs/reuse-map.md`.

## M3 — Harness adapters & fair comparison ✅ (landed)

Verified: 39 tests pass, `ruff` clean. Multi-seed run (62 cases × 5 seeds × 3 harnesses)
now yields **non-overlapping Wilson CIs** (raw 26.0% [21.2–31.4] · OpenCode 18.6% [14.5–23.5]
· Cortex 6.7% [4.3–10.2]); any-seed attack-success@n rises with attempts (raw 68%→81% at
seeds 5→8); over-refusal tradeoff now visible (Cortex 13.3%). `compare` shows cross-run deltas.

- [x] Harness presets for `codex_cli_raw`, `opencode`, `claude_code`, `cortex_wrapped` with
  **capability declaration** (tools / multimodal / max-context) shown as report glyphs.
  Real `raw_api`/`codex_cloud` adapters are thin follow-ons on the shared subprocess base.
- [x] **Attempt-budget normalization**: every harness gets the same `--seeds N` attempts per
  case; per-seed cost (tokens/wall) tracked. *Knob deferred:* hard token-cap for real adapters.
- [x] **`compare <run-a> <run-b>`** command — aligns by harness, prints ASR/over-refusal/utility
  deltas, writes `comparison.json`. Harness-delta (raw vs Cortex) remains the headline in-report.
- [x] **Reproducibility** (`scoring/stats.py`): pass@k unbiased estimator (attack-success@1 and
  @n), seed-level mean±std, Wilson + deterministic percentile-bootstrap CIs; **CI error bars** on
  the ASR chart and a Reproducibility & budget panel. Fixed a same-second `run_id` collision.

## M4 — Track Q (Code Quality & Output Security) ✅ (landed)

Verified: 49 tests pass, `ruff` clean. Track Q smoke (4 code-gen tasks × 4 harnesses) shows the
**Synapse USP**: `cortex_wrapped` (Codex+Synapse) reaches **grade A, 90% requirement coverage,
0 vulns/task, debt 0.25** vs raw Codex (grade C, 57.5%, 0.75 vulns/task) — +32.5 pts coverage —
*despite a similar base code_quality*, because Synapse tracks and validates every requirement.

- [x] **Synapse integration** (`gauntlet/synapse.py`): faithful offline shim mirroring
  `PlanGraphBuilder` (Understand/Deliver/Validate milestones) + `ValidationRuntime` (surfaces
  skipped required work), with a real-import seam (`backend=synapse` when the package is present).
  The `cortex_wrapped` harness = base + Synapse; coverage uplift drives the quality delta.
- [x] **SAST-lite** (`quality/sast.py`): 8 CWE patterns (CWE-89/798/327/78/95/295/502/22),
  zero-dep. Real Semgrep/Bandit/njsscan + SARIF are drop-in seams.
- [x] **Dependency/slopsquat** scan: flags malicious + hallucinated packages.
- [x] **Quality metrics** (`quality/metrics.py`): complexity, duplication, comment ratio,
  has-tests, has-error-handling, smell count, maintainability grade A–E.
- [x] **Code-quality judge** (`quality/judge.py`): per-dimension (architecture/readability/
  interface) heuristic; `CortexQualityJudge` is the production seam.
- [x] **Track Q report** (`report_quality.py`, shared CSS in `report_common.py`): coverage,
  maintainability-debt, vulns-by-CWE, judge radar, Synapse-advantage card, code explorer.
  `build_report` dispatches by track. `cortex benchmark run --track quality`.
- [x] **Realization (Phase 0c/0d/0b):** real **Bandit** (CWE) + **radon** + **ast** + **Semgrep**
  static analysis, and real dynamic functional verification on a self-contained runnable corpus —
  **pytest** for Python and **`node --test`** (Node built-in runner, native TS type-stripping, no
  third-party deps) for **TypeScript/JavaScript** (`gauntlet/analysis/`, `suites/quality/tasks.json`).
  Real SQL-injection (Python) and the TS upload API (CWE-78/95/22/798) are caught by static + dynamic.
- [ ] *Deferred:* SARIF normalization + njsscan, Trivy/OSV/GuardDog, multi-seed + `compare` for
  Track Q, real harness code-gen (`--live`), Docker isolation. See `realization-roadmap.md`.

## M5 — Track G (Generative Capability) ✅ (landed)

Verified: 56 tests pass, `ruff` clean. Track G smoke (3 app briefs, 34 features, × 4 harnesses ×
5 seeds) shows the **long-horizon USP**: `cortex_wrapped` (Synapse) reaches **91% feature
completeness / 100% honesty / composite 0.87** vs raw Codex **34% / 62% / 0.34** — +57 pts
completeness. The decay curve shows raw declining across feature position (~0.46→0.35) while
Synapse stays flat-high (~0.97).

- [x] **App-brief corpus** (`suites/generative/briefs.json`): e-commerce, ChatGPT clone,
  analytics dashboard in TS/Python; 10–12 ordered features each (the long horizon); guardrail
  variants (mandated stack).
- [x] **Composite scorer** (`generative/`): build gate → per-feature e2e completeness → visual
  fidelity → plan/trajectory judge; multi-seed with bootstrap CIs. *Deferred seams:* real harness
  code-gen, Playwright/REST/DB-state e2e, visual diffing.
- [x] **Plan/trajectory judge** (`generative/judge.py`): long-horizon reasoning score, separate
  from functional pass. `CortexGenerativeJudge` is the production seam.
- [x] **Long-horizon decay model**: raw harnesses decay across feature position; **Synapse keeps
  it flat** via milestones + ValidationRuntime (`generative/generate.py`, reuses `synapse.py`).
  Headline decay chart estimated at a fixed high sample for a smooth, honest curve.
- [x] **Honesty / over-claim** metric (raw harnesses claim failed features done; Synapse validates).
- [x] **Side-by-side app gallery**: a mock screenshot (SVG) per (brief, harness) showing delivered
  (green) vs dropped (grey) features. Real Playwright screenshots are the upgrade.
- [x] **Track G report** (`report_generative.py`): decay line, completeness-with-CI, dimensions
  radar, gallery, app explorer with feature checklist + milestone plan. `cortex benchmark run
  --track generative`.

## M6 — Judge integrity & calibration

- [ ] Jury + different-family judge; human-labeled calibration set; report κ / α (>0.8 target).
- [ ] Bias mitigations validated (position-swap effect, verbosity penalty, self-preference).

## M7 — Reporting polish & exports

- [ ] Full interactive report: filters (track/harness/technique/seed), heatmaps, radar,
  cost/efficiency panels, harness-delta highlights.
- [ ] PDF export (Playwright `page.pdf()`) + CSV export (PapaParse); branded theme.

## M8 — CLI, CI, and reproducible runs

- [ ] `cortex benchmark` subcommands wired into `src/cortex_cli`; Makefile targets.
- [ ] Dockerized reproducible run; pinned tool versions; seeded RNG.
- [ ] `agent-harness/acceptance-tests.md` green on a scheduled smoke run.

## M9 — Hardening & public leaderboard (optional)

- [ ] Anti-contamination refresh (time-fresh splits, procedurally generated injections).
- [ ] Public vs private board separation (held-out never published).
- [ ] Documentation + contribution guide for new cases/adapters.

## Sequencing notes

- Build **S → Q → G** by effort/ROI: S validates the safety thesis fastest and reuses the most
  mature scoring (side-effects + judge); Q is mostly deterministic tooling; G is the heaviest
  (sandboxed app runs + e2e) and lands last.
- Keep every milestone shippable: each adds cases/adapters/scorers without breaking the schema
  or the report contract.
