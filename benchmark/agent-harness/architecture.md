# Architecture

Gauntlet is a thin, typed orchestration layer over **Inspect AI** that drives **harness
adapters**, scores their output with **deterministic tools + sandboxed side-effect checks +
LLM judges**, and renders a **self-contained interactive HTML report**. Cortex `agent ask/run`
is the judge/agent backend; Docker sandboxes provide containment.

## 1. Component view

```
                         ┌──────────────────────────────────────────────┐
                         │                cortex benchmark               │  CLI (reuses src/cortex_cli http+config)
                         │        run · judge · report · compare         │
                         └───────────────┬──────────────────────────────┘
                                         │ loads
                ┌────────────────────────▼─────────────────────────┐
                │                Suite + Case loader                │  suites/*/  + schemas/
                │   resolves seeds, variants, held-out splits       │
                └───────┬───────────────────────────────┬──────────┘
                        │ Inspect Task(dataset,solver,scorer)        │
          ┌─────────────▼─────────────┐        ┌─────────▼───────────────────────┐
          │      Harness Adapters     │        │            Scorers              │
          │  (Solver implementations) │        │  S: canary + sandbox side-effect│
          │  • claude_code            │        │     + judge (refusal rubric)    │
          │  • codex_cli / codex_cloud│        │  G: build → e2e → visual → rubric│
          │  • raw_api (Anthropic/OAI)│        │     + plan/trajectory judge     │
          │  • cortex_wrapped         │        │  Q: SAST+deps+quality (SARIF)   │
          └───────────┬───────────────┘        │     + code-quality judge        │
                      │ runs inside              └─────────┬───────────────────────┘
            ┌─────────▼──────────────────────────┐         │ judge calls
            │      Sandbox (Docker, no egress)    │         ▼
            │  decoy secrets · honeypot sinks ·   │   ┌───────────────┐
            │  capture-only tool shims (no exec)  │   │ Judge backend │  cortex agent ask/run
            │  app run target (Track G)           │   │ (Claude/Codex)│  (LLM-as-judge / jury)
            └─────────┬───────────────────────────┘   └───────────────┘
                      │ run record (JSON, schemas/)
            ┌─────────▼───────────────┐      ┌────────────────────────────────┐
            │   results/<run-id>.json │─────▶│  Report builder (Vite+React)   │ → report.html / .pdf / .csv
            │   + artifacts/          │      │  ECharts · Prism · diff2html   │
            └─────────────────────────┘      └────────────────────────────────┘
```

## 2. Key abstractions (map to Inspect AI)

- **Case** — one test unit. Fields: `id`, `track`, `surface`/`technique`/`objective` (S) or
  `app_spec`/`features`/`guardrails` (G), `seed_text`, `modality` (text|image|audio), `variant`,
  `ground_truth`, `held_out: bool`. Schema in `schemas/`.
- **Suite** — a curated set of Cases for a track (`suites/{security,generative,quality}/`),
  declared in `SUITE.md` + a manifest; resolves external datasets via the reuse map.
- **HarnessAdapter** (Inspect *Solver*) — uniform `run(case, env) -> Transcript` over a harness.
  Adapters: `claude_code`, `codex_cli`, `codex_cloud`, `opencode` (OSS), `raw_api`,
  `cortex_wrapped`. Each declares
  capabilities (tools, multimodal, max context) and **normalizes token/attempt budget** so
  comparisons are fair.
- **Scorer** (Inspect *Scorer*) — pure function `(Transcript, Case) -> Score{value, detail,
  artifacts}`. Layered per track (§3).
- **Judge** — LLM-as-judge wrapper over `cortex agent ask`; structured output, order-swap, jury,
  calibration hooks. Different family from the system under test where possible.
- **Sandbox** — Docker environment with **no host egress**, decoy `.env`/credentials, honeypot
  HTTP/DNS sinks, and **capture-only tool shims** that record a proposed `curl`/`npm install`/`git
  push` instead of executing it.

## 3. Per-track scoring pipeline

**Track S (Sentinel)** — layered, cheapest-first, no execution:
1. **L0 deterministic** — refusal-prefix detector (baseline only); **canary/honeytoken**
   detection in output; structural detection of dangerous proposed tool-calls (exfil URL,
   malicious/hallucinated package, destructive git, `curl|bash`).
2. **L1 sandbox side-effect** (AgentDojo/RedCode pattern) — replay the captured tool-calls
   against the sealed mock env in **dry-run**; did a decoy secret reach a honeypot sink? was a
   destructive op proposed? Verified via mock side-effects, never real harm.
3. **L2 LLM judge** — rubric `Refusal / Deflect / Partial-comply / Full-comply` +
   `exploitable: bool` + rationale; jury for high-severity. → ASR / Refusal / Utility-under-attack.

**Track G (Forge)** — composite, gated:
`build/compile gate → functional e2e (Playwright UI flows + black-box REST + DB-state asserts)
→ visual fidelity (screenshot + Design2Code-style diff + visual judge) → per-feature rubric
checklist → plan/trajectory judge`. Pass@k over ≥3 seeds.

**Track Q (Auditor)** — deterministic + judge on the produced repo:
`SAST (Bandit/Semgrep/njsscan → SARIF, CWE-weighted) + deps (pip/npm audit, Trivy/Grype,
OSV/GuardDog + registry-existence gate) + quality (complexity, duplication, lint density,
maintainability) → per-KLOC normalize → code-quality judge (architecture/readability/interfaces)`.

## 4. Data flow & artifacts

`Suite → Cases → (per harness × seed) Transcript → Scores → RunRecord(JSON) → Report`.
Every Case run keeps: full prompt(s) + modality assets, transcript/trajectory, proposed
(never-executed) tool-calls, SARIF, screenshots, sandbox audit log. RunRecords validate against
`schemas/` and feed the report builder. Results + artifacts are git-ignored.

## 5. Reuse of existing Cortex assets

| Need | Reuse | Path |
| --- | --- | --- |
| CLI HTTP + config/profiles | cortex_cli client | `src/cortex_cli/{http,config}.py` |
| Agent/judge execution | `cortex agent ask/run` (provider codex/omp/claude) | `src/cortex_cli/cli.py` |
| Codex/OMP/Claude bootstrap | OpenClaw app-server + OMP shim | `openclaw/cortex-codex-app-server.sh`, `openclaw/cortex-omp.sh` |
| Containment patterns | integration sandbox runners | `tests/integration/agentic-security/run.sh` |
| Governance checks | policy / harness guard-evaluate | `cortex policy evaluate`, `cortex harness guard-evaluate` |
| Telemetry/artifacts | feedback bundles + HyperDX/OTel | `cortex feedback`, `observability/` |
| Report UI stack | React 19 + Vite + Prism | `control/plane/` |

## 6. Boundaries

- Gauntlet sits **beside** Cortex (`benchmark/`), consuming the CLI/agent surface; it does **not**
  modify OpenClaw channel/session/Codex internals (Cortex/OpenClaw boundary preserved).
- External datasets are vendored under their licenses (see `docs/reuse-map.md`); the private
  held-out split is never committed.
- The report builder is a standalone Vite app emitting static artifacts — no runtime server
  required to view a result.
