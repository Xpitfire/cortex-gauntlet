# Research: State of the Art

Synthesis of the SOTA review that grounds Gauntlet's design (June 2026). Each section
ends with what we **reuse** vs **improve**. Full citations at the end.

## 1. Adversarial: prompt injection, jailbreak, agentic misuse

| Work | Threat model | Scoring (how "attack success" is judged **without executing payloads**) | Reuse signal |
| --- | --- | --- | --- |
| **AgentDojo** (ETH, MIT) | Indirect/tool injection on tool-using agents; 629 security cases | **Deterministic `security()`/`utility()` over before/after environment state** — did money move / data leave | Best-in-class side-effect scoring; ships baseline attacks (IgnorePrevious, ImportantInstructions, …) |
| **InjecAgent** (UIUC) | Indirect injection into tool outputs; 1,054 cases | Parse ReAct output → success = agent calls the attacker tool | Direct-harm vs data-exfil split |
| **Agent Security Bench / ASB** (MIT) | DPI, **observation injection**, **memory poisoning**, PoT backdoor; ~90k | Success = agent calls all placeholder "attack tools"; ASR/Refusal/PNA | Multi-surface threat model |
| **RedCode** (Microsoft, NeurIPS'24) | **Closest to coding agents**; ~4,050 exec cases, 8 risk domains, 3 input formats | **Docker sandbox pre-loaded with decoy targets (`/etc/passwd`, fake servers); inspect real FS/process/network side-effects** | Sandboxed side-effect verification + canary decoys |
| **AgentHarm** (UK AISI) | Agent harmfulness, 110→440 behaviors | Per-task grading fns over tool-call trajectory + GPT-4o refusal judge; **private held-out set** | Refusal-vs-capability decoupling; anti-contamination |
| **HarmBench / JailbreakBench / AdvBench** | Chat-level jailbreak | Fine-tuned classifier / judge-LLM / **refusal-string match** (AdvBench = noisy, cautionary) | Use as *negative example* — avoid string matching |
| **garak** (NVIDIA, Apache-2.0) | Active scanner, 44 probes/32 detectors | String-match + HF classifiers + DecodeMatch + LLM-judge + **PyPI package-hallucination check** | Encoding probe family; package-hallucination detector |
| **PyRIT** (Microsoft, MIT) | Adaptive multi-turn (Crescendo/TAP/PAIR) | SelfAsk judge-LLM + content filters + deterministic substring | 30+ chainable converters (obfuscation) |
| **CyberSecEval / PurpleLlama** (Meta, MIT) | 251 textual + 1,000 visual injection; autonomous-cyber | **LLM-judge per "judge question"; 3-judge consensus** for autonomous ops | Visual injection set; judge-question pattern |
| **HackAPrompt** | ~600k real adversarial prompts, 10 levels | Exact match `"I have been PWNED"` | Canary-string pattern; attack ontology |

**Obfuscation / evasion catalog** (used across the works above): direct · "ignore previous
instructions" · role-play/DAN · base64/hex/rot13 · cipher (Caesar/Morse/SelfCipher) ·
leetspeak/char-substitution · payload splitting / token smuggling · zero-width &
whitespace Unicode · many-shot · low-resource language · past-tense reframing · ASCII art ·
plus social-engineering ("this is authorized, trust me, all good").

**Taxonomies to map against:** OWASP **LLM Top 10 (2025)** (LLM01 Prompt Injection, LLM05
Improper Output Handling, LLM06 Excessive Agency), OWASP **Agentic threats** (T2 Tool
Misuse, T3 Privilege Compromise, T6 Goal Manipulation, T11 Unexpected RCE), **MITRE ATLAS**.

**Reuse:** AgentDojo + RedCode side-effect scoring; ASB multi-surface model; AgentHarm
refusal/capability split + private set; garak/PyRIT obfuscation libraries; OWASP/ATLAS tags.
**Improve:** real coding-agent surfaces (repo files, READMEs, issues, MCP/tool output, CI
logs) not synthetic email suites; multi-turn/memory poisoning; canary-token + sandbox
side-effects over string/judge-only scoring; report **utility-under-attack** to penalize
over-refusal; anti-contamination via private + procedurally-generated injections.

## 2. Multimodal injection (image + audio)

| Work | Modality | Mechanism | Coding relevance |
| --- | --- | --- | --- |
| **FigStep** (AAAI'25, MIT) | Image | Render harmful request as "Steps to X" + blank list PNG; benign text asks to fill it in. SafeBench 500 Qs | A screenshot whose rendered text carries the real instruction |
| **MM-SafetyBench** | Image | Query-relevant SD+typography images; 5,040 pairs | "malicious intent lives in the image" |
| **JailbreakV-28K** | Image+text | Transfer text jailbreaks to vision channel; 28k | Text injections survive the image path |
| **VPI-Bench / Pop-up & GUI fine-print** | Image (agents) | Malicious directives in screenshots/UI/pop-ups override the task | **Directly models "UI screenshot says: also run `curl … | bash`"** |
| **AJailBench** (MBZUAI) | Audio | **TTS of text jailbreaks**, 118 voices/4 accents; 1,495 prompts; perturbation toolkit | Spoken brief: "…and push straight to main, skip tests" |
| **JALMBench** (ICLR'26) | Audio | 245k audio samples, 8 attacks, 5 defenses | Reusable TTS + voice-diversity pipeline |

**Reuse:** FigStep PNG renderer (MIT) and AJailBench TTS pipeline give a clean
**single text seed → text / image / audio** fan-out with shared ground-truth labels.
**Improve:** coding-specific multimodal cases (UI mockup, code-review screenshot hiding
"exfiltrate `.env`", architecture-diagram PNG, stack-trace image directing a malicious
install). Detect compliance via **canary/honeytoken in the proposed output**, never execution.

## 3. Agentic coding-harness capability (Track G)

| Work | Task | Scoring | UI/full-stack? |
| --- | --- | --- | --- |
| **SWE-bench** + **Verified/Live/Pro/Multimodal** | Repo issue → patch | Hidden FAIL_TO_PASS/PASS_TO_PASS tests, pass@1 | Multimodal=JS UI bug fixes; Live/Pro = **contamination-resistant freshness** |
| **Terminal-Bench 2.0** | 89 hard terminal tasks | Programmatic pytest in container; labels **(model+scaffold)** pairs | No UI |
| **Aider polyglot** | 225 Exercism, 6 langs | Hidden tests, pass@2; tracks "% well-formed edits" | Single-file |
| **SWE-Lancer** (OpenAI) | ~1,488 real Upwork gigs on Expensify **full-stack TS/JS** | **Pro-written end-to-end Playwright tests**; $ earned | Yes — real UI flows |
| **AppWorld** (ACL'24) | 750 interactive tasks, 457 APIs | **DB-state unit tests**; TGC vs **SGC** (whole-scenario) | Long-horizon robustness |
| **Design2Code / WebGen-Bench / FullStack-Bench** | Prompt/screenshot → app | CLIP+block-match (visual); browser-agent executes generated tests; **tri-layer UI+API+DB-state** | Yes — closest full-stack pattern |
| **BaxBench** | 392 backend tasks, 14 frameworks | REST functional + **security-exploit** tests | Backend + security |
| **Commit0 / DevBench** | Build libs / full SDLC | Test pass + coverage; staged PRD→UML→code→tests | Long-horizon feedback loops |

**Harness vs model:** vendors isolate the model with a minimal 2-tool scaffold (bash +
str_replace/apply_patch) and report **multi-trial averages**; product scaffolds
(Claude Code, Codex) are reported separately. **Scaffold variance often exceeds model
variance** — leaderboards rarely control attempts/token budget (a known confounder).

**Reuse:** SWE-bench-Live freshness; FullStack-Bench tri-layer (Playwright UI + black-box
REST + DB-state) + build gate; Design2Code visual diff; AppWorld SGC for long-horizon;
SWE-Lancer's pro-written e2e pattern. **Improve:** one unified run that combines
functional e2e + visual diff + build gating + **per-feature rubric checklist tied to
deterministic verifiers**, with attempt/token-budget normalization and one-shot
full-app briefs (e-commerce, ChatGPT clone) in TS/JS/Python.

## 4. Code quality & output-security (Track Q)

**Security of generated code:** SecurityEval (Py), CyberSecEval ICD (weggli+semgrep+regex,
~50 CWE; JS but **no TS**), SecCodePLT (dynamic tests + sandbox), CodeSecEval, LLMSecEval —
methodology converges on **MITRE Top-25 scenarios + CWE-tagged SAST**. TS is under-covered:
a gap we fill.

**Auto-scoring tools (all emit SARIF):** Python → **Bandit + Semgrep**; TS/JS → **Semgrep +
njsscan** (CodeQL optional, license-gated). Dependencies/supply-chain → pip-audit, npm audit,
**Trivy/Grype** (CVE), **OSV-Scanner** (`MAL-`) + **GuardDog/Socket** (malicious/slopsquat).
**~19.7% of LLM-suggested packages don't exist** and hallucinations recur (~58%) → gate every
agent-proposed package against the registry; log **hallucinated-package acceptance** as a
first-class metric.

**Quality/maintainability:** SonarQube Community (cognitive/cyclomatic complexity, code
smells, duplication, SQALE maintainability A–E) or radon/lizard + jscpd + Ruff/ESLint.
**LLM-as-judge** (CodeJudge, ICE-Score, CodeUltraFeedback) for architecture, readability,
interface cleanliness — with documented biases (position, verbosity, self-preference,
illusory-complexity up to −26.7 pts) mitigated by position-swap, per-dimension rubrics, and
a different-family judge.

**Reuse:** SARIF-normalized SAST + dependency scanners + Sonar metrics; CWE Top-25 mapping;
ICE-Score/CodeJudge rubric patterns. **Improve:** first-class **TS/JS** coverage; per-KLOC
normalization for fair harness-vs-harness comparison; slopsquat-acceptance metric; blind,
order-randomized judging.

## 5. Frameworks, judging, reproducibility, reporting

- **Framework foundation: Inspect AI** — Task = dataset + solver + scorer; first-class
  Docker/K8s sandboxing for untrusted agent code; native agent/tool/MCP (drives Claude Code
  & Codex CLI); model-graded scorers; **Inspect View** bundles to static HTML. Beats building
  standalone (which means re-implementing sandbox orchestration + transcript UI). Borrow
  G-Eval/DAG (DeepEval) and claim-decomposition (RAGAS) as *scorer patterns*; garak's
  probe→detector split for the red-team subset.
- **LLM-as-judge:** G-Eval style (auto-CoT eval steps → structured form-filling). For attack
  success use a discrete rubric `Refusal / Deflect / Partial-comply / Full-comply` +
  `exploitable_bool` + rationale — **not** refusal-string matching. For code quality use one
  isolated judge per dimension with behaviorally-anchored levels + a reference solution.
  Mitigate bias via order-swap, verbosity penalty, different-family judge / jury. Calibrate
  against a human-labeled set; report **quadratic-weighted Cohen's κ / Krippendorff's α** (>0.8).
- **Reproducibility:** pass@k unbiased estimator (n≥100); temp=0 is **not** deterministic →
  ≥3 seeds, report mean±std; Wilson intervals for proportions, bootstrap CIs for pass@k,
  cluster SEs on repo/task; contamination control via canary GUIDs + time-fresh splits +
  private held-out.
- **Reporting stack:** **Vite + React + `vite-plugin-singlefile`** → one self-contained HTML
  with run data inlined as JSON; **Apache ECharts** (best aesthetics/footprint) for charts;
  **react-markdown + Prism** for transcripts; **diff2html** for edits; **Playwright
  `page.pdf()`** for PDF (renders JS charts; react-pdf/WeasyPrint cannot); **PapaParse** for
  client-side CSV. Static single-file for per-run reports; served app only for large
  multi-run exploration — mirroring Inspect AI and HELM.

## Sources

**Adversarial:** AgentDojo 2406.13352 · InjecAgent 2403.02691 · ASB 2410.02644 · RedCode
2411.07781 · AgentHarm 2410.09024 · HarmBench 2402.04249 · JailbreakBench 2404.01318 ·
AdvBench/GCG 2307.15043 · garak 2406.11036 · PyRIT 2410.02828 · CyberSecEval/PurpleLlama
2408.01605 · HackAPrompt 2311.16119 · Gandalf 2501.07927 · OWASP genai.owasp.org · MITRE
ATLAS atlas.mitre.org · technique papers: Jailbroken 2307.02483, DAN 2308.03825, PromptInject
2211.09527, Many-shot (anthropic.com/research/many-shot-jailbreaking), low-resource 2310.02446,
CipherChat 2308.06463, past-tense 2407.11969, ArtPrompt 2402.11753, h4rm3l 2408.04811,
token-smuggling 2302.05733.
**Multimodal:** FigStep 2311.05608 · MM-SafetyBench (ECCV'24) · JailbreakV-28K 2404.03027 ·
HADES 2403.09792 · VPI-Bench 2506.02456 · Pop-up 2411.02391 · AJailBench 2505.15406 ·
JALMBench 2505.17568.
**Coding capability:** SWE-bench github.com/SWE-bench · SWE-bench Multimodal 2410.03859 ·
SWE-bench Live swe-bench-live.github.io · SWE-bench Pro 2509.16941 · Terminal-Bench tbench.ai ·
Aider aider.chat/docs/leaderboards · SWE-Lancer openai.com/index/swe-lancer · AppWorld
2407.18901 · Design2Code salt-nlp.github.io/Design2Code · WebGen-Bench 2505.03733 ·
FullStack-Agent github.com/mnluzimu/FullStack-Agent · BaxBench 2502.11844 · VisualWebArena ·
Commit0 github.com/commit-0/commit0 · DevBench.
**Code security/quality:** SecurityEval github.com/s2e-lab/SecurityEval · CyberSecEval
2312.04724 · SecCodePLT 2410.11096 · CodeSecEval 2407.02395 · LLMSecEval 2302.04012 · "Asleep
at the Keyboard" 2108.09293 · CWE Top-25 cwe.mitre.org/top25 · CodeQL codeql.github.com ·
Semgrep · Bandit · njsscan · Trivy · Grype · OSV-Scanner · GuardDog · Socket slopsquatting ·
SonarQube docs.sonarsource.com · radon · lizard · jscpd · CodeJudge 2410.02184 · ICE-Score
2304.14317 · CodeUltraFeedback 2403.09032 · code-judge bias 2505.16222.
**Frameworks/judging/reporting:** Inspect AI inspect.aisi.org.uk · lm-eval-harness · promptfoo ·
OpenAI Evals · HELM crfm.stanford.edu/helm · DeepEval G-Eval · RAGAS · G-Eval 2303.16634 ·
MT-Bench 2306.05685 · PandaGuard 2505.13862 · Anthropic evals
(anthropic.com/engineering/demystifying-evals-for-ai-agents) · pass@k 2107.03374 ·
nondeterminism (thinkingmachines.ai) · error bars 2411.00640 · LiveCodeBench 2403.07974 ·
ECharts · Playwright page.pdf · diff2html · vite-plugin-singlefile.
