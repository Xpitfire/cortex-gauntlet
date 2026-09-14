# Suite: quality (Track Q — Auditor)

Audits the code a harness produced (from Track G output or standalone code tasks). Mostly
deterministic tooling + a bias-mitigated code-quality judge. See `../../docs/scoring-and-judging.md`.

## Planned manifest (M4)

- `targets/` — code corpora to audit (Track G outputs are auto-enrolled).
- `sast/` — Bandit + Semgrep (Py), Semgrep + njsscan (TS/JS) configs → SARIF.
- `deps/` — pip/npm audit, Trivy/Grype, OSV-Scanner, GuardDog + registry-existence gate.
- `quality/` — complexity (radon/lizard/ESLint), duplication (jscpd), lint density, SQALE.
- `judge/` — per-dimension rubrics (architecture, readability, interfaces, idiom, docs).

## Scoring

SAST→SARIF (CWE-weighted, per-KLOC) + dependency findings (incl. **slopsquat-acceptance**) +
quality metrics + code-quality judge (blind, order-randomized, swapped).

## Notes

All metrics per-KLOC normalized for fair harness-vs-harness comparison; judge handles only what
deterministic tools can't (architecture, readability, interface cleanliness).
