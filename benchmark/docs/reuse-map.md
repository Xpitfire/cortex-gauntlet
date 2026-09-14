# Reuse Map — reuse vs build, per source

Gauntlet composes proven assets and adds the production-realism + visual layers they lack.
This table is the contract for what we vendor/adapt vs build fresh. Verify each license before
vendoring; keep provenance metadata with every imported dataset.

## Adversarial / Track S

| Source | License | Reuse | Build/improve on top |
| --- | --- | --- | --- |
| **AgentDojo** | MIT | Side-effect `security()/utility()` scoring idea; baseline attacks (IgnorePrevious, ImportantInstructions) | Coding-agent surfaces (repo/tool) instead of email suites |
| **RedCode** | check repo | Sandbox + decoy-target side-effect verification; risk-domain seeds | Capture-only (no execution) variant; TS/JS coverage |
| **ASB** | MIT | Multi-surface threat model (DPI/observation/memory) | Real memory-poisoning cases over Cortex sessions |
| **AgentHarm** | MIT (+safety) | Refusal-vs-capability split; private held-out discipline | Coding-objective grading functions |
| **garak** | Apache-2.0 | Encoding probe family; **PyPI package-hallucination detector** | Wire detectors into our SARIF-style finding model |
| **PyRIT** | MIT | Obfuscation **converters** (30+) as Case transforms | Deterministic, seedable transform library |
| **CyberSecEval / PurpleLlama** | MIT | Visual-injection set; judge-question + 3-judge consensus | Coding-specific judge questions |
| **HackAPrompt** | MIT | Canary-string pattern (`I have been PWNED`→our markers); attack ontology | Coding-objective canaries |
| OWASP LLM Top10 / Agentic, MITRE ATLAS | open | Taxonomy tags on every case | — |

## Multimodal / Track S

| Source | License | Reuse | Build/improve |
| --- | --- | --- | --- |
| **FigStep** (+SafeBench) | MIT | PNG renderer; "Steps to X + blank list" template | Realistic surfaces (terminal/README/diagram/pop-up) |
| **AJailBench / JALMBench** | open | TTS pipeline + voice/accent matrix; perturbation toolkit | Coding voice-brief cases ("push to main, skip tests") |
| **VPI-Bench / pop-up** | CC-BY-4.0 / paper | UI/screenshot-injection scenarios | Code-review screenshot, stack-trace image |
| **MM-SafetyBench / JailbreakV-28K** | open | "intent in the image" + text-to-vision transfer cases | Filter to coding-relevant subset |

## Coding capability / Track G

| Source | License | Reuse | Build/improve |
| --- | --- | --- | --- |
| **SWE-bench Live / Pro** | MIT / mixed | Freshness + anti-contamination methodology | App-gen freshness, not just repo fixes |
| **SWE-Lancer** | check | Pro-written **end-to-end Playwright** scoring pattern | Open full-app briefs (e-commerce, ChatGPT clone) |
| **FullStack-Bench / WebGen-Bench** | open | **Tri-layer UI+API+DB-state** functional scoring; browser-agent test exec | Unified build+functional+visual+rubric run |
| **Design2Code** | open | CLIP + block-match **visual diff** | Pair with functional, not visual-only |
| **AppWorld** | Apache-2.0 | **SGC** whole-scenario metric for long-horizon | Plan/trajectory grading |
| **BaxBench** | open | Backend **security-exploit** tests | Feed exploitable findings into Track Q |
| **Commit0 / DevBench** | MIT / open | Staged feedback loops; SDLC stages | Self-correction/recovery dimension |

## Code quality & output security / Track Q

| Source | License | Reuse | Build/improve |
| --- | --- | --- | --- |
| **Bandit / Semgrep / njsscan** | Apache/LGPL | SAST → **SARIF**, CWE mapping (Py + TS/JS) | Normalize all to one finding model, per-KLOC |
| **CodeQL** | OSS-only free | Deep taint queries where license allows | Optional; not required path |
| **Trivy / Grype / pip-audit / npm audit** | Apache/OSS | CVE/SCA over deps | Single dependency-finding model |
| **OSV-Scanner / GuardDog / Socket** | Apache/OSS | Malicious + slopsquat detection | **Registry-existence gate** + acceptance metric |
| **SonarQube Community** (or radon/lizard/jscpd/Ruff/ESLint) | LGPL/OSS | Complexity, duplication, maintainability | Standalone-tool fallback to avoid server dep |
| **CodeJudge / ICE-Score / CodeUltraFeedback** | open | Code-judge **rubric patterns** | Per-dimension, bias-mitigated judging |

## Framework / judging / reporting

| Source | License | Reuse | Build/improve |
| --- | --- | --- | --- |
| **Inspect AI** | MIT | Task/Solver/Scorer, **sandboxing**, agent/MCP, log viewer→static HTML; drives Claude Code & Codex | Our adapters/scorers/suites on top |
| **DeepEval (G-Eval/DAG), RAGAS** | open | Scorer *patterns* (eval-steps, claim-decomposition) | Our judge implementations |
| **Cortex `agent ask/run`** | in-repo | Judge/agent backend (provider claude/codex) | Wrap as Gauntlet Judge |
| **ECharts / Playwright pdf / diff2html / PapaParse / vite-plugin-singlefile** | OSS | Report stack | Branded Gauntlet report |

## Build-fresh (no good reusable source)

- Coding-agent **objective** corpus (secret exfil / malicious-dep / destructive-git / disable-control
  / backdoor) with canary-based detection.
- **Harness-delta** comparison harness (Cortex-wrapped vs raw) with budget normalization.
- One-shot **full-app briefs** with per-feature rubric checklists tied to deterministic verifiers.
- The **stunning interactive report** (no existing tool meets the bar).

## Vendoring rules

- Each imported dataset lands under `suites/<track>/vendor/<source>/` with a `PROVENANCE.md`
  (source URL, commit/version, license, date, filtering applied).
- License-incompatible or non-redistributable sets are referenced by fetch script, not committed.
- The private held-out split is never vendored into the public tree.
