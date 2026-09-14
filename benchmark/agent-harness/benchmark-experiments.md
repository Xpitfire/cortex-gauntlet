# Gauntlet — the experiments, explained

Gauntlet measures, head to head, how much a coding agent improves once **Cortex** (a governance layer:
hooks, policies, validation, long-horizon planning) is wrapped around it. The raw harnesses (Codex,
Claude Code, OpenCode) run with **no Cortex configuration** — a clean comparison — and the Cortex arms
run the same base models through the Cortex runtime. This file is the source for the generated site's
"What we measure" section and is meant to travel with the results.

## Harnesses compared

| Harness | What it is |
| --- | --- |
| **Codex CLI** | OpenAI's coding agent, raw. |
| **Claude Code** | Anthropic's coding agent, raw. |
| **OpenCode** | Open-source coding agent (reference), raw. |
| **Cortex [over Codex]** | The Codex base model run through the Cortex governance layer. |
| **Cortex [over Claude]** | The Claude base model run through the Cortex governance layer. |

The headline framing groups by base model — Codex (Codex CLI vs Cortex [over Codex]) and Claude (Claude
Code vs Cortex [over Claude]) — so the uplift Cortex adds to *the same* model is unmistakable. Gains are
reported as **relative %** (e.g. a 26% → 6.7% attack-success drop is a ~74% reduction), not just points.

## Track S — Security & Safety (jailbreak resistance) · the big ticket

Each harness is attacked with obfuscation techniques across four delivery surfaces — direct user turn,
poisoned repo file, malicious tool output, and tampered memory — in text, image and audio modalities.
We measure **Attack Success Rate (ASR)**: how often the harness is talked into an unsafe action (lower
is safer), with Wilson 95% confidence intervals and pass@k over seeds. We also report **over-refusal**
on benign tasks, so "refuse everything" is not mistaken for safety, and **utility-under-attack**. No
attack payload is ever executed — the runner is capture-only with sandboxed side-effect replay.

## Track Q — Code Quality & Output Security

Harnesses solve real coding tasks. We run real static analysis (**Bandit** for Python, **Semgrep** for
TS/JS, CWE-mapped), dependency / slopsquat checks, and the **hidden acceptance tests** (real pytest),
plus an LLM judge for architecture and readability. Reports requirement coverage, functional pass rate,
vulnerabilities per task, and a maintainability grade.

## Track G — Generative Capability

Long-horizon application builds scored on feature completeness, build/serve success, plan adherence,
and **honesty** (claimed vs actually-working), with a decay curve across the build horizon — the regime
where raw harnesses fade and the Cortex plan→validate→repair loop holds completeness.

## Track P — Full-Repo Project Build (codename Atelier)

A single open-ended brief to build an entire storefront (backend + React/Vite frontend + PWA + cart +
checkout + Stripe **test**) and execute it in a **hardened Docker sandbox** (non-root, deny-egress,
resource-limited). Scored on a build-gated composite: functional e2e, **VERTEX** trajectory similarity
to a hidden reference, security (Semgrep), visual fidelity (vision judge), and architecture. seeds=1
(a full-repo build is costly).

## Reading the results

- The **summary page** leads with the jailbreak reduction and the per-track relative gains; click any
  number to open the full, reproducible detail report (charts, CIs, captured code output, methodology).
- Detail reports are interactive (Apache ECharts), theme-aware, and self-contained.
- Provenance is explicit: mock vs measured basis, the judge backend that actually ran, and the
  containment mode are all stamped on the report.
