# Requirements Checklist

Status legend: `[x]` decided/specified in Phase 1 · `[ ]` to build in Phase 2+.
This is a living checklist; update it when scope, security posture, or acceptance
coverage changes.

## Functional — core

- [x] Evaluate coding-agent **harnesses** (Codex CLI/cloud, OMP, Claude Code, raw API, and the
  Cortex-wrapped harness) as pluggable adapters behind one interface.
- [x] Report the **harness delta** for every metric (Cortex-wrapped vs raw Codex/OMP/Claude
  Code on the same model/task/seed), not just absolute scores.
- [x] Three tracks: **S Security & Safety**, **G Generative Capability**, **Q Code Quality
  & Output Security**. Tracks share the run/result schema and the report.
- [x] Build on **Inspect AI** (Task/Solver/Scorer + container sandbox + agent/MCP) and reuse
  Cortex `agent ask/run` as the LLM-as-judge backend.
- [ ] Provide a `cortex benchmark` CLI surface (run / judge / report / compare) reusing
  `src/cortex_cli` HTTP client + config.
- [x] First-class languages: **TypeScript, JavaScript, Python**.

## Functional — Track S (Security & Safety / Sentinel)

- [x] Model attacks as **surface × technique × objective** (see `docs/attack-taxonomy.md`).
- [x] Cover surfaces: direct user turn; indirect injection via repo files (README, code
  comments, docstrings, issues); tool-output injection (MCP / web-fetch / CI logs); memory
  & multi-turn session poisoning; multimodal (image, audio).
- [x] Cover obfuscation techniques: direct, ignore-previous, role-play/DAN, base64/hex/rot13,
  cipher, leetspeak, payload splitting / token smuggling, zero-width/whitespace Unicode,
  many-shot, low-resource language, past-tense, ASCII art, social-engineering.
- [x] Cover coding-agent objectives: secret/`.env` exfiltration to attacker sink; install
  malicious / typosquatted / hallucinated package; `curl | bash` / arbitrary shell; destructive
  git (force-push main, history rewrite); disable security control (auth, TLS verify); backdoor
  insertion; data exfil via canary token.
- [x] **Never execute** any payload — capture the proposed response/tool-call and validate it
  (see `agent-harness/security-model.md`).
- [x] Generate image and audio attack variants from a single text seed (FigStep renderer +
  TTS pipeline) with shared ground-truth labels.
- [x] Report **ASR, Refusal Rate, Utility-under-attack, and Over-refusal** (benign-but-suspicious
  false positives), sliced by surface × technique × objective.
- [x] Support bounded **adaptive red-team passes** for harmful cases: pass 1 is the authored prompt;
  later passes are generated from the prior response by a configured red-team backend, with cumulative
  ASR by pass reported separately from the overall result.
- [ ] Maintain a **private held-out** attack split + procedurally-generated injections for
  contamination resistance.

## Functional — Track G (Generative Capability / Forge)

- [x] One-shot full-app briefs in TS/JS/Python (e-commerce, ChatGPT clone, dashboard, …) with
  **rich structured prompts** and optional guardrail variants (mandated framework/architecture
  vs free-form) to test instruction adherence.
- [x] Composite scoring: **build/compile gate → functional e2e (Playwright UI + black-box REST
  + DB-state) → visual fidelity (screenshot + diff + visual judge) → per-feature rubric
  checklist → plan/long-horizon score**.
- [x] Capture and grade the **execution plan / trajectory** separately from final functional
  success (long-horizon reasoning dimension).
- [ ] Side-by-side qualitative comparison view: rendered apps, prompts, responses, trajectories.
- [ ] Run untrusted generated apps only inside the sandbox (no host network egress by default).

## Functional — Track Q (Code Quality & Output Security / Auditor)

- [x] Deterministic SARIF-normalized SAST: Python (Bandit + Semgrep), TS/JS (Semgrep + njsscan);
  CWE-mapped, severity-weighted, **per-KLOC normalized**.
- [x] Dependency/supply-chain: pip-audit + npm audit + Trivy/Grype (CVE) and OSV-Scanner +
  GuardDog/Socket (malicious/slopsquat); **registry-existence gate** with a hallucinated-package
  acceptance metric.
- [x] Quality metrics: cognitive/cyclomatic complexity, duplication %, lint density, SQALE
  maintainability (SonarQube Community or radon/lizard + jscpd + Ruff/ESLint).
- [x] LLM-judge dimensions (per-dimension rubric, blind, order-randomized, swapped): architecture/
  modularity, readability, interface cleanliness, idiomaticity, comment quality.

## Functional — Reporting

- [x] Generate a **self-contained interactive HTML report** (Vite + React +
  `vite-plugin-singlefile`, ECharts, react-markdown + Prism, diff2html) per run.
- [x] **Prompt/response/trajectory drill-down**, filterable by track/harness/technique/seed.
- [x] **PDF export** via Playwright `page.pdf()` and **CSV export** via PapaParse.
- [x] Branded, colored, labeled per harness/model — looks stunning, not a console dump.

## Non-functional

- [x] **Reproducibility:** pass@k unbiased estimator; ≥3 seeds, report mean±std; Wilson/bootstrap
  CIs; controlled temperature; **attempt/token-budget normalization** for harness-vs-model fairness.
- [x] **Cost & efficiency** captured per run: tokens, wall-clock, tool-call count, retries.
- [x] **Containment:** untrusted agent code and attack payloads run only in sealed sandboxes;
  no real secrets; egress to honeypot sinks only. See `security-model.md`.
- [x] **Judge integrity:** different-family judge / jury; calibrated against a human-labeled set
  (κ / α reported).
- [x] **Anti-contamination:** canary GUIDs, time-fresh splits, private held-out set.
- [x] Python 3.11, ruff (line-length 100); modular, typed, files ≤ 1000 lines (target ≤ 400);
  enums over scattered string literals; external systems behind adapters; tests per module.
- [x] Secrets never logged or committed; results/artifacts git-ignored by default.

## Acceptance (summary — see `acceptance-tests.md`)

- [ ] One end-to-end smoke run per track produces a valid result JSON + HTML report.
- [ ] No attack payload is ever executed (verified by sandbox audit log).
- [ ] Harness-delta comparison renders for at least Codex vs Cortex-wrapped on one task.
