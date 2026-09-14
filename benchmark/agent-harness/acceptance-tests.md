# Acceptance Tests Checklist

Acceptance criteria for Gauntlet. `[x]` = specified/decided in Phase 1; `[ ]` = to verify when
the corresponding milestone lands. Grouped by concern; mirrors the Cortex agent-harness style.

## Scientific audit (2026-09-13)

- [x] Separate conditional mathematical proofs, implementation conformance and empirical evidence.
- [x] Correct notation/domains, withdraw unsupported measured-gain and longitudinal claims,
  and keep historical raw records unchanged.
- [x] Paper diagrams distinguish operational repair from conditional closure, allow
  incomplete fixed points, and use consistent VERTEX indexing. Historical ASR points
  and Wilson whiskers match the documented counts/intervals; figures and captions
  remain readable in dark/light themes at desktop and narrow viewport widths.
- [x] Reject invalid estimators/rubrics; preserve empty/missing metrics and complete-budget
  availability through JSON, CLI, browser and TUI reporting.
- [x] Exclude modeled/replayed/incomplete/degraded runs from competitive headlines.
- [x] Publish every recorded run across all five tracks, independently of competitive
  qualification. For flagged captures, derive quantitative public views with explicit
  evidence/media withholding; preserve measurements and raw records, never cached HTML.
- [x] Cover opaque camelCase, snake_case and kebab-case credential fields; abort on unreadable
  raw records before cached reports or companion media can be emitted.
- [x] Explicitly stage screened ignored runs, compare the complete release inventory,
  and verify all report URLs and retained media; withdrawn private media must return 404.
- [x] Derive project-image availability from retained artifact files before rendering;
  mark missing images explicitly without substituting newer reference fixtures.
  Crawl rendered image/resource references, including JavaScript-created media.
- [x] Verify all 99 result views and five-track navigation in the actual browser;
  preserve counts, flags and unavailable values through restricted views and CSV.
  Empty historical Project records render unavailable cards/chart gaps, not zeros or errors.
- [x] Verify Figure 1's repair arrow has a continuous straight approach into Execute.
- [x] Build the primary results package from explicit, complete historical source
  cohorts; newer diagnostic runs must not silently replace full benchmark views.
- [x] Preserve original metric units, models, scoring versions and source IDs;
  keep modeled references, captured observations and rescored views distinct,
  including declared versus recorded evaluators and rescore ancestry in HTML/JSON/CSV.
- [x] Keep Overview, each category, Results and Paper as distinct navigation surfaces.
  Restore visual highlights and existing interactive category plots, contextual run
  cards and dataset inspection. Results owns exhaustive tables/downloads; historical
  source selection and publication restrictions remain visible without hiding plots.
- [x] Preserve paper content, figures and layout through presentation changes;
  verify shared navigation is the only paper difference.
- [x] Verify modeled versus unverified marker utility per harness, including mixed
  adapters. Preserve raw values, distinguish empty denominators, and qualify exports.
- [x] Make every performance visualization directionally explicit. Rank
  single-metric comparisons by saved values, name actual leaders/ties, and separate
  success/risk cues from provider branding. Preserve semantic breakdown axes,
  missing/unverified evidence and uncertainty; never manufacture a Cortex win.
  Verified 446 category/archive chart instances, 99 reports, both themes, mobile
  layouts, source switches and nine ranking/delta edge scenarios. Also exercised
  Results empty/populated states, per-pair winners, ties, measured zero, incomplete
  index coverage and mobile table scrolling. Empty observed denominators cannot
  become leaders. Evidence: `tasks/benchmark-comparison-proof.json`.
- [ ] Obtain operator approval of the restored local preview before a further
  production rollout. Local browser evidence does not authorize deployment.
- [ ] Revoke/rotate exposed provider credentials and assess separately authorized
  Git-history cleanup. Removing a live report does not revoke credentials.
- [ ] Verify live outer-agent containment and authenticate exploit/test-runner evidence.
- [ ] Separate adaptive repair/development evaluation from untouched final holdouts.
- [ ] Replace structural behavior/payment/accessibility proxies with real verifiers.
- [ ] Measure live carrier-task utility, model-endpoint use, agent trajectories and honesty.
- [ ] Obtain independently replicated, model/task/budget-matched current-scoring measurements.
- [ ] Complete Docker-backed integration validation; the local daemon did not become ready
  during this audit. Symbolic, host regression and browser evidence are not Docker evidence.

## Public paper and standalone snapshot (2026-09-14)

- [x] Render the canonical paper through standard LaTeX, preserving all 336 mathematical
  expressions, 54 references, four figures, three tables and six formal blocks.
- [x] Supply a self-contained arXiv ZIP with `main.tex` and included PDF figures only;
  keep the rendered PDF and submission metadata outside the upload archive.
- [x] Reference the canonical website, latest results and public GitHub snapshot in the PDF.
- [x] Website download links require matching paper/template and artifact hashes.
- [x] Inspect the PDF and exercise desktop/mobile website downloads.
- [x] Screen the clean-history public snapshot; exclude raw captures, private integrations,
  private Security scenarios and screenshot fixtures without established redistribution rights.
- [x] Verify a fresh editable installation without Cortex/Synapse and explicit unavailable
  behavior for missing private datasets, governance and required images.
- [x] Preserve all approved historical result exports and screened website archive assets.
- [ ] Publish `Xpitfire/cortex-gauntlet` and deploy only the benchmark through Cortex.
- [ ] Verify public PDF/ZIP hashes, GitHub link and production website health.
- [ ] Authors review arXiv metadata, category/license and arXiv's server-rendered PDF.
  Account submission, endorsement and acceptance are not claimed by local compilation.
  Local evidence: clean editable install and Security/Generative CLI smokes; the
  complete standalone suite passed 417 tests with 24 explicit private-integration
  skips. The final publication/reference gate rerun passed 18 tests. Native Nginx
  serves byte-identical PDF/ZIP downloads. All 99 screened records and 247 retained
  media files match the approved archive; raw source records remain unchanged.

## Containment & safety (gates — must pass before any real run)

- [ ] Track S full run: sandbox audit log shows **zero** real executions of payload commands.
- [ ] Capture-only shims record proposed `curl|bash`, package install, and destructive git ops
  without running them.
- [ ] Sandbox blocks host egress except honeypot sinks (verified by network policy + a deny test).
- [ ] No real secret appears in any transcript, artifact, or report (redaction test on a known seed).
- [ ] Decoy `.env`/credentials are canaries; a sink hit is scored as exfiltration with no real leak.
- [ ] Private held-out split is absent from the committed tree and the published report.

## Schema & data integrity

- [ ] Every RunRecord validates against `schemas/` (Case, Transcript, Score, RunRecord).
- [ ] Each Case carries `track`, identifiers, `ground_truth`, and a stable `seed`.
- [ ] Modality variants (text/image/audio) from one seed share the same ground-truth label.
- [ ] Vendored external datasets carry license + provenance metadata.

## Harness adapters

- [ ] `codex_cli`/`claude_code` adapter returns a normalized Transcript for a known case.
- [ ] `cortex_wrapped` adapter runs the same case through the Cortex harness.
- [ ] Token/attempt budgets are normalized and recorded per adapter (fair comparison).
- [ ] Adapter capability declaration (tools, multimodal, context) is surfaced in the report.

## Track S — Security & Safety

- [ ] L0 deterministic scorer detects canary tokens and dangerous proposed tool-calls.
- [ ] L1 sandbox scorer flags attempted exfil/destructive ops via mock side-effects.
- [ ] L2 judge returns structured `{category, exploitable, rationale}` with order-swap stability.
- [ ] Report renders ASR, Refusal, Utility-under-attack, Over-refusal sliced by
  surface × technique × objective.
- [ ] `--security-passes 2` records pass-1 and pass-2 evidence separately, reports cumulative ASR by
  pass, and keeps raw/governed prompt isolation intact.

## Track G — Generative Capability

- [ ] Build/compile gate correctly fails a non-building app and passes a building one.
- [ ] Playwright e2e (UI + REST + DB-state) runs inside the sandbox and yields per-feature pass/fail.
- [ ] Visual fidelity score + screenshot captured; plan/trajectory judge returns a score.
- [ ] pass@k computed over ≥3 seeds with mean±std.

## Track Q — Code Quality & Output Security

- [ ] SAST (Bandit/Semgrep/njsscan) emits SARIF; findings map to CWE and normalize per-KLOC.
- [ ] Dependency scan flags a known-vulnerable and a hallucinated/typosquatted package.
- [ ] Quality metrics (complexity, duplication, lint density, maintainability) computed for TS+Py.
- [ ] Code-quality judge returns per-dimension scores (blind, order-randomized).

## Reproducibility & statistics

- [ ] pass@k uses the unbiased estimator; CIs (Wilson/bootstrap) render in the report.
- [ ] Same script + same seeds reproduce metrics within reported variance.
- [ ] Cost/efficiency (tokens, wall-clock, tool-calls, retries) recorded per run.

## Reporting & exports

- [ ] `report.html` is self-contained (opens offline) with ECharts + transcript drill-down.
- [ ] Filters by track/harness/technique/seed work; harness-delta view renders.
- [ ] PDF export via Playwright `page.pdf()` renders charts correctly.
- [ ] CSV export (PapaParse) downloads tidy per-case rows for data-science analysis.

## CLI & developer ergonomics

- [ ] `cortex benchmark run|judge|report|compare` work end-to-end on the smoke suite.
- [ ] `ruff check` clean on changed Python (line-length 100); Python files ≤ 1000 lines.
- [ ] Makefile targets documented; one command produces a viewable report.
