# Reporting Design — the visual layer

The report is a first-class deliverable, not an afterthought. **If a run's output is a console
dump, the run failed.** Every run produces a **self-contained, interactive, branded HTML report**
plus PDF and CSV exports.

## Delivered public-site hierarchy

The static Python renderers remain the implementation; the Vite/React stack below
is an earlier design target, not a description of the current build.

- **Overview** (`index.html`): graphical Security spotlight and five track cards,
  with a visible modeled/captured source switch. Highlights use named saved metrics,
  not a newly pooled score or silently substituted diagnostic.
- **Category pages** (`security.html`, `quality.html`, `generative.html`,
  `project.html`, `bugfix.html`): existing native plots, galleries, evidence
  explorers, code viewers and exports; searchable dataset details and experiment
  cards add context. `*-captured.html` keeps the captured collection separate.
- **Results** (`results.html`), immediately before **Paper**: exhaustive package
  tables, original/rescored alternatives, archive links and JSON/CSV downloads.
- **Paper** (`docs.html`): the established document and figures. Visual-site changes
  must not alter its content or CSS; shared navigation changes are checked separately.

`gauntlet/site_visuals.py` decorates already-screened canonical report HTML. A
run-relative base preserves retained asset paths; category jump links explicitly
target the category URL rather than the base directory. Overview/category decoration
is separate from the shared comparison CSS/JS used by canonical reports. Paper
imports neither comparison addition. Dataset cards consume `public_record()`
projections, never raw captures, and restricted media stays withheld.

Legacy missing metrics render as unavailable, not fabricated zero scores. Captured
Security utility retains its numeric history but is labeled unverified; mixed
adapter runs retain each harness's own modeled/unknown provenance.

Publication and historical-utility notices belong after the methodology footer,
below the report content and category explorers—not between navigation and the
report heading. Preserve their wording and compact inline evidence/status labels.

## Performance direction and comparison order

- Single-metric comparisons are ordered by actual saved values: lowest first for
  ASR, over-refusal and debt; highest first for coverage, completeness and scores.
  Values are not inverted, normalized, pooled or rescored to manufacture a winner.
- Direction is prominent at each chart. Failure magnitude uses risk cues; the
  actual leading point estimate is identified by harness and value, independently
  of provider branding. Equal values are ties; missing/unverified values are not
  ranked. “Lowest/highest recorded” is not a claim of statistical superiority.
  Empty Security denominators are also excluded from cards, bars, confidence
  whiskers, breakdowns and pairwise comparisons. Overview receives the saved counts
  separately from screened records; package exports retain the original values.
- Highlight cards use the same ordering and name the metric that determines it.
  Cortex is a leader only where its recorded value supports that statement.
  Overview uses an explicit per-metric direction flag for both ordering and
  best-value selection. Empty comparisons say that no measurements are available.
- Technique, feature-position, pass, dimension and other semantic axes retain
  their meaning. Grouped/radar/line charts label direction and explain that color
  identifies a harness, not an overall rank; they do not invent a pooled winner.
- Results preserves base-model groups and orders measured arms within each pair.
  Its existing qualified Gauntlet Index keeps its stated normalization: only
  complete overall values determine row rank, with independent family leaders.
  Neither Cortex branding nor partial coverage earns an overall award. Narrow
  layouts use sparse chart ticks and horizontally scrollable, readable tables.
  Relative-change cards label the delta separately; direction pills belong to the
  raw-to-Cortex metric values, not the change magnitude.
- Reordering must keep values, confidence intervals, labels and tooltips attached
  to the same harness. Verify actual layout widths, both themes and all archived
  reports. The protected Paper is excluded from this presentation change.

## Visual reference — Artificial Analysis (artificialanalysis.ai)

The target look is **Artificial Analysis**: clean, editorial, lots of negative space, vivid
per-brand accent colors on a light base, value labels on every bar, dashed gridlines, and brand
logos as axis markers. We reproduce these specific motifs (mapping their "models/providers" onto
our **harnesses/models**):

| AA motif | What it is | Gauntlet mapping |
| --- | --- | --- |
| **Highlights card row** | 2–3 hero metric cards at top, each a self-contained bar chart with a colored-square title icon, an `Updated`/`New` badge, and a "Higher/Lower is better" subtitle | Top row: **Security composite** (higher better), **Generative composite** (higher better), **Cost per pass / task** (lower better), **Harness delta** (Δ) |
| **Per-brand color + logo axis** | Provider identity independent of quality | Retain identity colors for multi-series plots; use explicit rank/direction cues in single-metric comparisons |
| **Value labels in/atop bars** | The number printed inside or above each bar | Same — never make the reader estimate from the axis |
| **Dashed gridlines + airy layout** | Light dashed horizontal guides, generous padding, neutral type | Same; light theme primary, optional dark |
| **Hatched / patterned bars** | Texture denotes special states ("Estimate", "Not currently available") | Texture denotes **judge-only (no deterministic confirmation)**, **held-out**, **estimate**, or **partial coverage** — with a pattern legend |
| **Highlighted leading bar** | Best recorded point estimate gets a clear marker | Highlight the actual metric leader, including ties; never assign a win solely because the harness is Cortex |
| **Capability glyphs under bars** | AA's lightbulb = reasoning model | Glyphs per harness: multimodal, tool-use, sandboxed, budget-normalized |
| **Left sidebar of sub-metrics** | Vertical nav of related indices, each with an `Updated` badge | Nav of **dimensions** per track (jailbreak, injection, complexity, maintainability, …) |
| **Segment toggle tabs** | "Open Weights / Proprietary", "Reasoning / Non-Reasoning" | Tabs: **by track**, **product-scaffold vs raw vs Cortex-wrapped**, **by language**, **by modality** |
| **Top-right export icons** | link / image / table glyphs on each chart | **Copy-link / PNG / CSV** per chart; **PDF** for the whole report |
| **Row/model selector + filters** | "28 of 538 models" + filter control | Harness/case selector + filter by technique/objective/seed |
| **Chart watermark + info expander** | "Artificial Analysis" mark; `ⓘ` "+"-expandable methodology note | Gauntlet watermark; every chart has an `ⓘ` expander linking to methodology |

ECharts covers all of this (grouped/stacked bar with `itemStyle.decal` for hatching, custom
`graphic` watermark, label formatters, brand-color palette). Keep the typography neutral
sans-serif and the palette per-brand-accent-on-light — restrained, not rainbow.

## Stack (decided)

| Concern | Choice | Why |
| --- | --- | --- |
| App | **Vite + React 19** | Matches `control/plane/` stack; component-driven, declarative |
| Bundle | **`vite-plugin-singlefile`** | One `report.html` with run data inlined as JSON — opens offline, emailable, CI artifact |
| Charts | **Apache ECharts** | Best aesthetics/footprint (~80–100 KB tree-shaken); radar, heatmap, sankey, bar/line |
| Transcripts | **react-markdown + Prism** | Prompt/response/trajectory rendering with code highlighting (Prism already in repo) |
| Code diffs | **diff2html** | Side-by-side edit diffs for generated/edited code |
| PDF export | **Playwright `page.pdf()`** | Renders live JS charts (react-pdf/WeasyPrint cannot) |
| CSV export | **PapaParse** (client-side) | Tidy per-case rows for data-science analysis |

Static single-file is the default per-run artifact (mirrors Inspect AI `bundle` + HELM). A served
multi-run explorer app is optional later for large cross-run analysis.

## Information architecture

1. **Header / hero** — run id, date, models × harnesses compared, headline composites, and the
   **harness-delta callout** (Cortex-wrapped vs raw Codex/OMP/Claude Code).
2. **Overview dashboard**
   - Track composites per harness (grouped bar, labeled & colored per harness/model).
   - **Radar** across dimensions per harness.
   - **Harness-delta** diverging bars (Δ per metric, green/red).
   - Cost/efficiency panel (tokens, wall-clock, tool-calls, cost-per-pass).
3. **Track S panel**
   - **Heatmap** ASR over surface × technique (per harness), drill to objective × modality.
   - Refusal vs Utility-under-attack vs Over-refusal (stacked / scatter).
   - Modality-gap view (text-refused but image/audio-complied).
4. **Track G panel**
   - Build → functional → visual → plan funnel; per-feature checklist grid.
   - Side-by-side rendered-app screenshots; pass@k with CIs.
5. **Track Q panel**
   - Vulns/KLOC by CWE (bar), maintainability A–E, complexity/duplication, slopsquat-acceptance.
   - Judge dimensions (architecture/readability/interfaces) radar.
6. **Case explorer (drill-down)** — filter by track/harness/technique/objective/seed; open any
   case to see full prompt(s) + modality asset, transcript/trajectory, proposed (never-executed)
   tool-calls, SARIF findings, sink hits, and **judge rationale with confidence**.
7. **Methodology footer** — seeds, temperature, pass@k config, CIs, judge models, κ/α calibration,
   dataset provenance/licenses, and the containment attestation (zero real executions).

## Design principles

- **Show the breakdown, never an opaque single number** — every composite expands to its
  dimensions and to the underlying evidence.
- **Statistical honesty** — error bars / CIs on every aggregate; mean±std across seeds visible;
  no silent truncation (if coverage was capped, the report says so).
- **Color & labels per harness/model**, consistent legend, accessible palette, light/dark.
- **Evidence one click away** — a number always links to the transcript/SARIF/sink that produced it.
- **Branded** (Gauntlet theme) and genuinely good-looking — the audience expects stunning plots.

## Data contract

The report consumes a single validated `RunRecord` JSON (see `schemas/`). The builder is pure:
`RunRecord → report.html`. No network calls at view time; assets inlined. PDF/CSV derive from the
same RunRecord so all three exports agree.

## Build & invocation (planned)

- `cortex benchmark report <run-id>` → builds `results/<run-id>/report.{html,pdf,csv}`.
- Report app lives in `benchmark/` report builder package; Vite build emits the single file;
  a headless Playwright pass renders the PDF from the built HTML.

## LaTeX paper and public source snapshot (2026-09-14)

`gauntlet.paper` consumes the canonical Markdown paper in `gauntlet/docs.py`.
Pandoc parses the prose, tables, equations and references; the four authored SVG figures
are converted to included PDFs. `paper_template.tex` uses the official ICLR 2027 style
with the standard `article` class, named authors and an explicit preprint header.
The `.sty` and `.bst` files are unmodified from `ICLR/Master-Template` revision
`46ed6f4c6cef5b175dde23639e77d44c3463b230`; no conference acceptance is implied.
Native pdfLaTeX produces the paper PDF, distinct from browser-print export of a result report.

```sh
cd benchmark
.venv/bin/python -m gauntlet.paper --output site/public/paper
```

The build requires Pandoc, `rsvg-convert`, pdfLaTeX and `pdfinfo`. Uploading the resulting
source ZIP does not require those converters: it contains `main.tex`, both official
ICLR style files and eight included PDF figures, with an embedded bibliography.
`submission.txt` links the official
arXiv source/metadata rules. arXiv currently defaults to TeX Live 2025; inspect its own
generated PDF before author submission. A local TeX Live 2026 build is not an arXiv
server compilation or acceptance claim.

The site exposes the PDF, arXiv ZIP and submission instructions only when the manifest's
canonical-paper, exporter/template/style, publication-URL and artifact hashes match.
The PDF's first-page footnote
links `https://benchmark.cortex.a2olabs.com`, `https://cortex.a2olabs.com`, and the
public `Xpitfire/cortex-gauntlet` source.
The website's “Cite this work” block is excluded from PDF/LaTeX.
Contributions follow the Introduction in both formats. The PDF is a dated paper snapshot,
not a claim that archived runs were newly executed.
The exporter compares the complete mathematical-expression multiset, including
inline/display kind, against the canonical source. Exporter-code, template/style
or publication-URL changes invalidate existing download metadata.
Footnote destinations use `PAPER_URL`, `CORTEX_URL` and `REPOSITORY_URL`.
Formal web blockquotes become flush-left, numbered `amsthm` theorem/proposition
environments, with native proofs and paragraph-ending QED symbols. Export rejects
nonconsecutive statement, figure or table numbers and mismatched anchors. Tables use native
numbered captions; prose references and canonical anchors follow reading order in both formats.
SVG subscripts use positioned ordinary glyphs rather than font-dependent Unicode
subscript letters.
Mathematical quantities and estimator labels are authored in math spans, including
`$g_{\text{score}}$` and `$\mathrm{ASR}@1$`; family symbols use the same notation
as their set definition. The manuscript is self-contained: experiment descriptions
state the task, comparison arms, procedure, sample coverage, numerical outcomes
and limitations rather than pointing to internal run IDs, local files or raw
metadata fields. Operational provenance remains in companion release artifacts.
Expression-multiset parity preserves authored math but cannot detect a quantity
mistakenly authored as code, so publication review also inspects remaining code
spans and the rendered PDF.
The main Results section introduces the safety, coding-outcome and reference-rank
comparisons. Appendix B contains complete quality, repair, to-do, storefront and
reference-ranking evidence. Synthetic result illustrations are excluded from every
paper format; empirical conclusions are grounded only in retained benchmark outcomes.
`gauntlet/paper_results.py` shares frozen, reconciled numeric values between the tables
and deterministic theme-aware SVGs. Publication never reads private results at runtime.
The current paper contains eight vector figures and nine tables; the source ZIP embeds
every figure as PDF. Compact tables remain unbroken, figures prefer their local context,
and each appendix begins on a fresh page. Inspect every final PDF page at print size:
successful compilation alone does not detect orphaned table headers or poor float placement.

The public repository has independent history and contains benchmark source, authored
public fixtures, the paper and quantitative exports. Private Security scenarios are
operator-supplied JSON, not embedded public source. Raw captures, private Cortex/Synapse
code, production configuration and uncleared screenshot fixtures/media are excluded.
The existing screened interactive archive remains on the canonical website. A standalone
checkout cannot regenerate the historical package without authorized source records;
that failure must precede mutation of the existing archive.
An unreadable source record is a separate privacy failure: its corresponding cached
report is revoked before the build aborts, while unrelated screened archives are retained.
Required publication notices are attached after the complete methodology footer, so
category explorers and appended diagnostics remain above them. The common report builder
validates this anchor before writing the destination; specialized renderers return HTML
without persisting it. A missing anchor must preserve an existing published report.

Scientific editing preserves source measurements while correcting their interpretation.
Define symbols at first use, state the actual evaluator backend and missingness conventions,
and distinguish conditional mathematics from implementation behavior and historical evidence.
Citation hover cards must describe the cited studies, not reintroduce unsupported comparisons.
Keep prose direct; avoid promotional claims, repeated caveats and unnecessary em-dash asides.
Appendix P5 distinguishes the any-success and all-success subset estimators, their opposite
monotonicity in the subset size, and their different expectations under independent trials.
Symbolic finite examples support those distinctions without claiming a general formal proof.
