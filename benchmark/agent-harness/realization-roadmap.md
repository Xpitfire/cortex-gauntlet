# Realization Roadmap — from mocks to real

Plan to replace every mock/stub with real inputs, real analysis, and real harness execution,
and to wire all deferred seams. Sequenced so each step is shippable (tests + ruff + smoke) and
keeps the invariants: **attack payloads are never executed** (capture-only), and **generated
code/apps run only in a sandbox**.

## Environment (verified, June 2026)

- **TTS:** `say` (macOS) → real WAV. **Raster:** `rsvg-convert`, `inkscape` (SVG→PNG).
- **Static:** Python `ast` (real, zero-install); Bandit/Semgrep/radon pip-installable to `.venv`.
- **Dynamic:** `pytest`, `node`/`npm`/`npx`, **Docker** all present.
- Not yet present (installable when needed): Playwright, PIL, cairosvg, Semgrep.

## Phase 0 — Real inputs & real analysis (prerequisite; do first)

- **0a. Real multimodal attack assets** ✅ — Track S audio via `say` (spoken attack instruction,
  verified ~8–14s of real speech), images rasterized SVG→PNG via `rsvg-convert` (real 660×182
  raster). Graceful fallback to tone/SVG when host tools are absent. (`gauntlet/modality.py`)
- **0b. Proper, runnable inputs** ✅ — Track Q corpus rebuilt as self-contained, runnable Python
  modules with **hidden ground-truth tests that actually exploit the flaws** (real SQL injection,
  eval, salt-ignoring hash, path traversal); good code is Bandit-clean. Track G app briefs enriched
  into proper complex specs (instruction + architecture/data-model + acceptance).
- **0c. Real STATIC analysis** ✅ (Python; wired into Track Q) — `gauntlet/analysis/static.py`:
  real **Bandit** (security → CWE) + **radon** (complexity/LOC) + stdlib **`ast`** (structure),
  installed into `.venv`. Track Q Python tasks now report real CWEs (89/327/78/95/295/703/…).
  *Next:* TS/JS via Semgrep/njsscan + SARIF normalization (Phase 2); refine corpus so good code is
  bandit-clean.
- **0d. Real DYNAMIC analysis** ✅ (wired into Track Q) — `analysis/dynamic.py` runs the module's
  hidden tests with **pytest** → real functional pass-rate. The SQL-injection test actually
  exploits the vibe-coded variant (returns a row) and passes on the parameterized one. *Next:*
  Docker isolation (Phase 4) for untrusted Track-G apps; `vitest`/`node` for TS/JS.
- **0e. Shared analysis layer** ✅ — `gauntlet/analysis/` (static + dynamic + shared Finding/
  CodeMetrics model) is the reusable home for Track Q (audit) and Track G (functional).

## Phase 1 — Real harness adapters (code-gen) ✅ (Track Q wired)

`gauntlet/livegen/`: `CodeGenAdapter` abstraction + `SubprocessCodeGen` base that drives a real
CLI in a temp workspace and captures the files it writes. Real adapters for **codex** (`exec`),
**claude** (`-p`), **cortex** (`agent run --provider …`, Synapse-governed), **opencode**; a
**FakeCodeGen** makes the generate→analyze→score pipeline testable without an authed CLI.
**Track Q `--live --provider {codex|claude|cortex[:…]}`** generates the module from the spec
(function-signature contract), then runs the *same real Bandit + pytest analysis*. Mock stays
default; missing/failed CLIs degrade gracefully to a valid runrecord. *Next:* Track G live needs
the real build/e2e of Phase 3 to score a generated app; cortex workspace capture is best-effort
until the Cortex runtime exposes the workspace locally.

## Phase 2 — Real security tooling (Track Q) ✅ (core landed)

- ✅ **Real Semgrep** for TS/JS via a local offline ruleset (`analysis/rules/security.yaml`,
  CWE-tagged) → **SARIF normalized** into the shared Finding model (`analysis/sarif.py`,
  `analysis/semgrep_local.py`). `analyze_static` now dispatches Python→Bandit/radon/ast,
  TS/JS→Semgrep. Track Q gained a TypeScript task (real Semgrep catches CWE-78/95/22/798).
- ✅ **Dependency registry-existence gate** (`analysis/deps.py`): imports checked against PyPI
  (hallucinated/slopsquat) + known-malicious list; graceful offline. pip-audit installed.
- ✅ **TS/JS dynamic functional verification** via Node's built-in runner (`node --test`, native
  type-stripping on Node 23+, no third-party deps; `analysis/dynamic.run_node_tests_files`). The
  TypeScript upload task now scores a real functional pass-rate (good 2/2, vibe-coded 0/2) instead
  of skipping — Track Q dynamic now covers Python **and** TS/JS.
- [ ] *Deferred:* njsscan, Trivy/Grype + OSV-Scanner + GuardDog (CVE/malicious DB), npm audit,
  pip-audit CVE wiring, severity-weighted per-KLOC scoring.

## Phase 3 — Real e2e (Track G) ✅

`gauntlet/generative/e2e.py`: a real **build gate → start server → Playwright UI assertions +
black-box REST + state checks → screenshot → teardown** runner (`run_e2e`). Proven against a
runnable fixture full-stack app (`suites/generative/fixtures/todo-app/`, UI+REST+in-memory state):
all checks pass on the working app, failing checks are detected, the build gate fails closed —
with real Chromium. `gauntlet/generative/live.py` wires it into **Track G `--live`**: a real
harness generates the app (via the Phase-1 codegen adapter), then the e2e runner MEASURES it →
a real completeness instead of a modeled one (tested end-to-end via FakeCodeGen writing the
fixture). Playwright+Chromium installed in `.venv`. *Next:* Docker isolation for untrusted apps
(Phase 4); visual diffing; more live briefs; npm/vite build apps.

## Phase 4 — Containment hardening (Docker)

Materialize the sandbox: L1 side-effect replay (Track S) and running generated apps/tests (Q/G)
in containers with `--network none`/honeypot-only egress, decoy secrets, ephemeral workspaces,
and an audit log asserting zero real payload executions.

**Track P landed (✅):** ephemeral, non-root (`--user 1000`), `--cap-drop ALL`,
`no-new-privileges`, CPU/mem/pid/time-limited sandbox (`project/sandbox.py` + `sandbox/Dockerfile`,
Node 22 + pnpm + Python + Playwright). Two-phase: install with registry egress → serve+probe with
**default `--network none`**. Controlled egress via `project/egress_proxy.py` — a stdlib CONNECT
**allowlist proxy** (`--network-policy stripe-test`) that tunnels only Stripe **test** hosts; the
candidate sits on an `--internal` network and the dual-homed proxy is the sole route out. Added a
**Semgrep security signal** (`analysis/security.py`, weight .09 in the composite) and **TUI workspace
binding** (the live repo tree is persisted to `results/<run>/sandbox/<harness>/repo/` and browsable in
the IDE). Host-side e2e (`tests/test_e2e_probe.py`) validates launch→serve→probe→score without Docker.
See `track-p-runbook.md`.

## Phase 5 — `cortex benchmark` CLI

Wire `run / judge / report / compare` into `src/cortex_cli` (reuse `http.py`, `config.py`, and
`cortex agent ask/run` as the agent + judge backend); Makefile targets.

## Phase 6 — Vite + React single-file report

Replace the Python report-v0 with the production stack: Vite + React + `vite-plugin-singlefile`,
**vendored ECharts inlined** (fully offline single file), consuming the identical RunRecord JSON;
PDF via Playwright `page.pdf()`, CSV via PapaParse.

## Phase 7 — Real Synapse integration

`pip install -e` the Synapse library; delegate to real `PlanGraphBuilder` / `ValidationRuntime` /
`RecoveryCoordinator` (the shim already mirrors them); extend Synapse where the benchmark needs it
and contribute back.

## Phase 8 — Statistical & cross-track polish

Multi-seed + `compare` for Q and G; real LLM judges (`CortexJudge` wired) with human-calibration
(κ / α); contamination control + private held-out for Q and G.

## Status

- **Phase 0 essentially complete:** 0a ✅ (real TTS + PNG), 0b ✅ (runnable Track Q corpus with
  exploit tests), 0c ✅ (real Bandit/radon/ast static), 0d ✅ (real pytest dynamic, wired), 0e ✅
  (shared `analysis/` layer). 61 tests pass, ruff clean. Track Q is now end-to-end real on Python:
  cortex+Synapse grade A / 100% functional vs raw grade C / 39% (real SQL-injection caught by both
  static and dynamic). **Phase 1 ✅ (Track Q)**: `gauntlet/livegen/` live code-gen adapters
  (codex/omp/claude/cortex/opencode + Fake), `--live` wired into Track Q. **Phase 2 ✅ (core)**: real
  Semgrep TS/JS via local ruleset + SARIF normalization + dependency registry gate; Track Q now
  multi-language (Bandit Python + Semgrep TS). 72 tests pass, ruff clean. **Public results site
  deployed** via Cortex (live at benchmark.cortex.a2olabs.com, public/no-SSO; `gauntlet site`
  + `cortex deploy`). **Phase 3 ✅**: real build+serve+Playwright/REST e2e runner
  (`generative/e2e.py`) wired into Track G `--live`; verified against a runnable fixture with real
  Chromium. 76 tests pass, ruff clean. **Next:** Phase 4 (Docker isolation) → 5 (cortex CLI) →
  6 (Vite report) → 7 (real Synapse).
