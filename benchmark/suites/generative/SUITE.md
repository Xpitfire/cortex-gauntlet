# Suite: generative (Track G — Forge)

One-shot full-app briefs in TS/JS/Python with rich, structured prompts and optional guardrail
variants. See `../../docs/dimensions.md` and `../../docs/scoring-and-judging.md`.

## Planned manifest (M5)

- `briefs/` — app specs (e-commerce, ChatGPT clone, dashboard, …): goal, feature list,
  per-feature acceptance, optional mandated framework/architecture (guardrail variant).
- `verifiers/` — Playwright e2e (UI flows), black-box REST checks, DB-state assertions per brief.
- `reference/` — reference screenshots/specs for visual diff (Design2Code-style).
- `rubrics/` — per-feature checklist + plan/trajectory rubric.

## Scoring

build gate → functional (Playwright UI + REST + DB-state) → visual fidelity → per-feature
rubric → plan/trajectory judge. pass@k over ≥3 seeds. Apps run **only** in the sandbox.

## Notes

Each brief ships free-form and guardrailed variants to measure instruction/guardrail adherence
and the **harness delta** (Cortex-wrapped vs raw Codex/OMP/Claude Code).
