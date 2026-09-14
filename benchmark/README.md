# Cortex Gauntlet

Gauntlet evaluates coding-agent harnesses across five tracks:

| Track | What is evaluated |
| --- | --- |
| Security | Authored prompt-injection cases, canary disclosure and proposed harmful actions |
| Quality | Functional tests, static analysis and output security |
| Generative | App-building trajectories, functional checks and available visual evidence |
| Project | A storefront task with functional, architecture, UX and visual evaluation |
| Bugfix (`repo`) | Repository repair tasks and hidden evaluator tests |

Whether governance improves outcomes is a hypothesis tested within each comparison,
not a general guarantee. Modeled diagnostics are synthetic and excluded from competitive
headlines. Historical observations are not made comparable merely by sharing a chart.
Unavailable signals remain unavailable rather than being scored as perfect zeros.

## Paper, source and results

- [Paper](https://benchmark.cortex.a2olabs.com/docs.html)
- [Rendered LaTeX PDF](https://benchmark.cortex.a2olabs.com/paper/cortex-gauntlet.pdf)
- [arXiv source ZIP](https://benchmark.cortex.a2olabs.com/paper/cortex-gauntlet-arxiv.zip)
- [Latest results and source qualifications](https://benchmark.cortex.a2olabs.com/results.html)
- [Standalone public repository](https://github.com/Xpitfire/cortex-gauntlet)

The public repository is an independent, clean-history source snapshot. It retains
the `benchmark/` layout and includes the paper and quantitative result exports under
`published/`. Raw execution captures, private Cortex/Synapse code, deployment configuration,
private Security holdouts and screenshot fixtures without established redistribution
rights are not included. The hosted site retains the screened interactive archive.
Historical package regeneration requires the authorized source records; `gauntlet site`
fails explicitly without them and does not erase the existing archive on that failure.
A malformed source record revokes its own untrusted cached report, not unrelated archives.

## Standalone quickstart

From the repository root, using Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./benchmark
.venv/bin/gauntlet --help
.venv/bin/gauntlet run --track security \
  --adapters mock:codex_cli_raw,mock:cortex_wrapped \
  --judge heuristic --limit 1 --seeds 1 --no-site
GAUNTLET_VERTEX_MODEL=none .venv/bin/gauntlet run --track generative \
  --judge heuristic --limit 1 --seeds 1 --no-site
```

These commands exercise modeled diagnostics, not live harness measurements. `--no-site`
keeps newly generated local reports separate from the historical public package.
Use an editable checkout: suite resources are source-relative; this snapshot is not
advertised as a self-contained wheel or PyPI release.

The core CLI uses the Python standard library. Optional features have real prerequisites:

- `pip install -e "./benchmark[tui]"` installs the Textual experiment UI.
- Quality/Bugfix scoring needs the pinned analyzers in `benchmark/pyproject.toml`,
  Node for JS/TS tasks and the selected sandbox backend. Missing tools cannot supply
  a clean score. `cd benchmark && uv sync` installs public development dependencies.
  The developer environment is pinned to Python 3.13 in `.python-version`; the pinned
  Playwright/greenlet combination does not support Python 3.14.
  Run `npm ci` in `benchmark/` to install the locked ESLint/TypeScript toolchain before
  scoring JS/TS or running the full suite: `uv run --frozen pytest tests -q`.
- Browser probes need Playwright and its Chromium browser; Docker sandbox execution
  needs a working local Docker daemon. Live harnesses need separately installed,
  authenticated CLIs and may incur provider charges.
- Live Cortex/Synapse integration requires an authorized upstream installation and
  governance/template resources. Their absence is not replaced by a fake integration.
  Optional private integration tests skip explicitly when the package is unavailable.
- Required licensed screenshot fixtures must be supplied locally before those live
  multimodal cases can run. Missing required images are unavailable, not text-only
  substitutes. Project visual scoring likewise needs reference images and a real judge.

## Safety and interpretation

The authored corpus draws on published research; proposed reuse of external datasets
in design documents is not evidence that those datasets are installed or redistributed.
Gauntlet's implementation is its native Python runner, not an Inspect AI integration.

Security uses synthetic canaries and an in-memory L1 side-effect model. Configuration
isolation is **not** process or network containment. Run live adversarial harnesses only
in a disposable, appropriately isolated environment without real secrets or production
access. Do not interpret captured proposals or regex classifications as observed
execution of side effects.

The public Security corpus contains no private split. `--held-out` requires an authorized
JSON array supplied through `GAUNTLET_PRIVATE_SECURITY_SCENARIOS`; every entry must match
`gauntlet.agentic_corpus.Scenario` and set `held_out: true`. Enum fields use their string
values; families must be unique safe identifiers. File paths must be relative, without
parent traversal or Git administrative paths. Merely labeling a
split held-out does not establish independent construction or freedom from contamination.
Tests hidden from an evaluated app are evaluator boundaries, not necessarily secret datasets.

Interactive reports load ECharts, CodeMirror and JSZip from CDNs. Local HTML generation
does not imply an entirely offline browser experience. Chart leaders follow the measured
metric direction and ties; no harness receives an automatic winner highlight.

The [driver guide](BENCHMARK.md), [scoring contract](docs/scoring-and-judging.md) and
[reporting design](docs/reporting-design.md) provide detail. Older milestone and reuse
documents contain design history and proposals, not additional public-release guarantees.
Commands involving Cortex production profiles or parent-repository files are upstream
maintainer operations, not standalone setup steps.

## Additional CLI operations
Track Q runs real functional tests on the generated code: **pytest** for Python and **`node --test`**
(Node ≥ 23 on PATH, native TS type-stripping, no npm deps) for TypeScript/JavaScript. Without those
tools the affected cells degrade gracefully to `– skip` (static analysis still runs). It also adds
**ruff + mypy** lint/type cleanliness over the generated tree (fast, no extra generation) and reports a
**per-check success rate** that counts each check and categorizes it as *functionality* (tests),
*quality* (lint + types), or *security* (findings) — so a 6/7 cell with clean lint/types is not
misrepresented as a total failure. The same per-check rate is added to Track R (Bugfix) and Track G.

**Live-run prerequisites (only for `--live`).**
- **Track G (generative)** probes the generated app against a deterministic local
  OpenAI-compatible stub. This tests integration behavior, not a learned local language model.
- **Track S (security)** requires a supported authenticated harness and the configured
  judge. Heuristic and modeled results remain distinct from live judge evidence.
- Adaptive security probes are opt-in: `--security-passes 2 --red-team auto` keeps pass 1 as the
  original one-shot result, then lets a red-team generator write one follow-up user turn after a refusal.
  The report shows cumulative ASR by pass.
- **Heavy cells** (e.g. `brand_clone` 1:1 UI reconstruction) can exceed the per-call timeout; raise it for
  a re-run with `GAUNTLET_HARNESS_TIMEOUT=<seconds>` (and prefer `--seeds 1` so it's one long attempt, not
  N × timeout).

**Artifacts & loading old runs.** Every run (`run` *and* `tui`) writes the same artifacts to its
result dir: `runrecord.json` (the canonical record) + `report.html` (the interactive report). Reopen
any past run — from either command — in the IDE viewer (read-only, nothing re-runs):

```
gauntlet tui --load results/quality-20260616-...        # a run dir
gauntlet tui --load .../runrecord.json                  # or the record file
gauntlet report <run-id>                                # just rebuild report.html
gauntlet retry-timeouts <run-dir>                       # re-run ONLY the timed-out cells, patch in place
gauntlet rescore <run> [--tracks all] [--judge …] [--vision-judge …] [--vertex-ref …]  # re-score persisted run, no harness re-run
gauntlet pause   <run-id>                               # pause a running suite gracefully (resume later)
```

**Re-score without re-running the harness (`rescore`).** After a scoring change, apply it to a finished
run of **any track** without re-invoking the (expensive) build harness — `rescore` reuses the persisted
generated code + captured execution observation and re-runs the *current* scoring, writing a corrected
`runrecord.json` + `report.html` to `…-rescored/`. It skips only **generation, never evaluation**: the
judges you configure run in the loop (CLIP/LLM `--vision-judge` on the persisted screenshots, the LLM
`--judge` on the captured transcript).

- **project** reconstructs each arm from `sandbox/<h>/{repo, result.json}` → `score_project` (no Docker).
- **quality / repo** replay the persisted code through the real scorer (re-execute the hidden tests).
- **generative** reuses the feature/build/visual observation and recomputes only the static signals
  (lint/security) on the persisted app code (no SLM-sidecar/probe re-run).
- **security** re-judges the captured response (and lists cells needing a real re-run + verdict flips).

`rescore <run>` re-scores that run (track auto-detected); `rescore --tracks project,quality,…|all`
re-scores the latest run of each. Per-track failures stay isolated. Continue any Track-S cells that need
a real re-run with `gauntlet suite --resume <…-rescored> --tui --live --provider <list>`.

`retry-timeouts` reloads a completed Track-S record and re-runs just the cells that timed out (those
missing from the grid) with the same adapters the run used, merges them back, re-aggregates, and
rewrites `runrecord.json` + `report.html` + the site — so a long run with a couple of slow cells
doesn't need re-running. A cell that times out again stays in the report's "Skipped" section.

It is also wired into the Cortex CLI as a decoupled passthrough — every argument after
`benchmark` is forwarded verbatim to `gauntlet`, so all options below work there too:

```
cortex benchmark suite \
  --live --tui \
  --tracks security,quality,generative,project,repo \
  --provider codex,omp,claude,opencode,cortex,cortex:omp,cortex:claude \
  --judge claude \
  --vision-judge claude-vision \
  --vertex-ref auto \
  --network-policy stripe-test \
  --keep-containers \
  --synapse-iterations 3
cortex benchmark tui  --track quality
cortex benchmark run  --track security --limit 5
cortex benchmark tui  --load results/quality-<run-id>     # reopen a past run in the IDE
cortex benchmark report <run-id>                          # rebuild report.html
```

Project accepts one qualitative vision judge per run: `--vision-judge claude-vision` or
`--vision-judge clip`. To compare both without rerunning the harnesses, run the suite once, then
rescore the persisted Project run with the other judge:

```
cortex benchmark rescore --tracks project --vision-judge clip
```

Project VERTEX reference selection is a run parameter: `--vertex-ref auto` resolves to VERTEX-QE
for live Project/rescore runs and to the authored reference for offline mock fixtures. Use
`--vertex-ref authored|brief|repo|qe|consensus` to force a specific mode. The legacy
`GAUNTLET_VERTEX_REF` env var is only a low-level fallback for helper scripts.

`suite` runs every track in order with the right per-track seed policy baked in — **Security/Quality/Bugfix
`--seeds` (default 3, worst-of-N: any seed failing = fail, to catch live non-determinism)**, while
**Generative and Project run once** (a full build per seed is costly) — then rebuilds the site once. Flags: `--live --provider <list>`, `--tracks`,
`--seeds`, `--tui`, `--judge`, `--network-policy`, `--keep-containers`, `--vision-judge`, `--vertex-ref`,
`--synapse-iterations`, `--security-passes`, `--red-team`, `--no-site`. It runs headless
(console progress); `--tui` runs the TUI-capable tracks in one Textual IDE (a section per track,
Bugfix headless). The single-track `tui` command remains for one track at a time.

### Main params (`run` / `tui`)

| Param | Applies | Meaning |
| --- | --- | --- |
| `--track {security,quality,generative,project,repo,bugfix}` | both | which suite to run (default `security`); `bugfix` is an alias of `repo` (Track R) |
| `--live` | both | generate with a **real** harness CLI instead of the mock (needs auth) |
| `--provider <list>` | both (live) | comma-separated harnesses: `codex`, `claude`, `opencode`, `cortex[:codex\|claude]` — one record, multi-harness compare (e.g. `codex,cortex,cortex:claude`) |
| `--seeds N` | both | repeats per item for Security/Quality/Bugfix (worst-of-N); default 1 for `run`/`tui`, 3 for `suite` |
| `--only <ids>` | both | run only these item ids (comma list) — for cheap subsets |
| `--limit N` | both | run only the first N items (0 = all) |
| `--no-tui` | `tui` | force the plain console observer (auto when no TTY / CI) |
| `--judge {auto,heuristic,cortex,claude}` | `run` / `suite` / `tui` | scoring judge (`auto` uses the direct Claude-CLI judge for live security and heuristic otherwise; `cortex` is guard-blocked) |
| `--security-passes N` | Security `run` / `suite` / `tui` | bounded adaptive attack turns per harmful case; default `1`, use `2` for a red-team follow-up |
| `--red-team {auto,heuristic,claude}` | Security `run` / `suite` / `tui` | follow-up generator for passes after the first; `auto` uses Claude in live semantic runs |
| `--vision-judge {auto,heuristic,clip,claude-vision}` | Project live/rescore | qualitative Project judge; only one per run, rescore persisted runs to compare another |
| `--vertex-ref {auto,authored,brief,repo,qe,consensus}` | Project live/rescore | VERTEX reference mode; `auto` = QE for live/rescore, authored for mock |
| `--network-policy {none,stripe-test}` | Project live | container egress policy; `none` denies all, `stripe-test` allows Stripe test hosts through the allowlist proxy |
| `--keep-containers` | `suite` Project live | keep built Project apps served on localhost ports for qualitative review until the TUI closes |
| `--synapse-iterations N` | Project Cortex arms | max plan→validate→repair passes; default 3 lets Cortex repair gaps and sandbox build/functional failures |
| `--adapters <list>` | `run` (security) | explicit mock adapter specs, e.g. `mock:codex_cli_raw,mock:opencode` |

### Live subsets (cheap, for testing the live path)

Live runs cost time + tokens per `item × provider`, so scope both down while iterating:

```
# one task, two harnesses, live — watch it in the IDE
gauntlet tui --track quality --live --provider codex,cortex --only shop_cart

# first 2 security cases, mock vs cortex, fewer seeds
gauntlet run --track security --live --provider codex,cortex --limit 2 --seeds 2

# adaptive security: original prompt + one red-team follow-up turn
gauntlet run --track security --live --provider codex,cortex --limit 2 --security-passes 2 --red-team auto

# the single generative brief (chat app + local SLM), codex only, headless console
# needs a local model: `ollama serve` + `ollama pull qwen2.5:0.5b`
gauntlet tui --track generative --live --provider codex --no-tui
```

> Note: `claude` / `opencode` need to be run from a real terminal (the in-IDE sandbox blocks
> `--dangerously-skip-permissions`), and `opencode` needs a fresh `opencode auth login` for GPT-5.5.
> If OpenCode's host token is invalidated, preflight drops that arm and reports
> `opencode auth token invalidated` instead of hanging the suite.
> Raw harnesses do not inherit user-global Codex/OMP/Claude/OpenCode config. They get sterile tool homes
> with only allowlisted auth files linked from your normal profile or explicit `GAUNTLET_*_AUTH_JSON`
> / managed-home source variables, so experiments reuse logins without importing global MCP/skills/hooks.
> OpenCode auth is seeded via `XDG_DATA_HOME/opencode/auth.json`; `OPENCODE_CONFIG` is intentionally
> not set because current OpenCode treats it as a config file path, not a directory.
> `cortex` / `cortex:omp` / `cortex:claude` wrap the same local base CLIs as raw Codex/OMP/Claude, with the Cortex template
> plus Synapse loop under test.

### Experiment IDE (live TUI)

A three-pane, mouse-driven IDE (`gauntlet/tui/`, built on Textual) shows each experiment live:
a tree of `track → group → item × harness` with status glyphs (✓ pass · ✗ fail · ⚠ error ·
– skip), a top progress bar, the selected cell's prompt + a syntax-highlighted file browser/editor
+ metrics + any exception traceback, and a terminal pane that streams output. One failing
experiment becomes an ⚠ error cell (with traceback) — it never aborts the run. Keys: `f` follow,
`e`/`c` expand/collapse, `w` wrap, `y`/`p`/`ctrl+y` copy, `q` quit (mouse-clickable throughout).

**Selection & clipboard (Mac + Linux).** The editor is a real selectable code view (tree-sitter
highlighted): click into it and drag to select; `ctrl+c` copies the editor selection (Textual
copies a focused editor). You can also drag-select text in the other panes. Copy works three ways,
all cross-platform:
- The editor's own selection → `ctrl+c` (when the editor is focused).
- Your terminal's native copy of the on-screen selection — **Cmd+C** (macOS) / **Ctrl+Shift+C**
  (most Linux terminals); handled by the terminal emulator.
- App keys that push the *logical* content to the system clipboard via OSC 52 (identical on every
  OS): `y` copy the current file, `p` copy the prompt, `ctrl+y` copy the current selection. (OSC 52
  works in iTerm2/kitty/WezTerm/Alacritty/recent gnome-terminal and tmux with `set-clipboard on`;
  macOS Terminal.app doesn't support OSC 52 — use Cmd+C there.) Quit is `q` / `ctrl+q`.

The event/runner core (`tui/events.py`, `tui/runner.py`) is framework-agnostic and reusable for
future experiments; the Textual app and the console logger are just two observers of the stream.

- **Track S** — 13 obfuscation techniques, direct/repo/tool/memory surfaces, multimodal
  (image/audio), L0+L1+judge scoring, multi-seed pass@k with Wilson/bootstrap CIs, `compare`.
- **Track Q** — SAST-lite (8 CWEs) + dependency/slopsquat + complexity/maintainability + code
  judge; **Synapse** drives the cortex_wrapped advantage (grade A, 90% requirement coverage).
- **Track G** — a ChatGPT-style app wired to a **local** small model (offline); build→serve→e2e
  (incl. a live chat round-trip)→CLIP visual→plan **capability composite**; **long-horizon decay**
  (raw harnesses degrade, Synapse stays flat); honesty metric; side-by-side screenshot gallery.
- **Track P (Project, *Atelier*)** — one open-ended prompt builds a **full repo** (a Zalando-style
  storefront: backend + PWA frontend + cart/checkout + Stripe test payment + tests). Scored on a
  **multi-signal vector**: objective (build/functional-e2e/PWA-a11y/code-health/robustness) +
  **VERTEX** capability+architecture cross-similarity (cosine + DTW distance-decay, chance-normalized;
  `analysis/vertex.py`; `--vertex-ref auto` uses reference-free VERTEX-QE for live runs and authored
  fixtures for mock) + **LLM judges** (Claude-vision visual fidelity, code/architecture, UX) gated
  by objective signals. Runs in a **hardened Docker sandbox** (non-root, deny-egress, resource-limited)
  with Playwright capture. `seeds=1` (costly). `gauntlet run --track project` (mock works offline;
  `--live --provider …` builds with a real harness + runs it in the sandbox — needs Docker; set
  `GAUNTLET_VISION_JUDGE=1` to enable the Claude-vision judge). **Synapse drives the cortex arm**:
  on `--live`, a `cortex`/`cortex:claude` arm runs the real Synapse `Orchestrator`
  (plan→generate→observe→validate→repair) over the storefront requirements and writes its planning
  trail to `<run>/sandbox/<harness>/synapse/` (`plan.json`, `PLAN.md`, `progress.jsonl`,
  `verdict.json`); raw arms single-shot (the honest A/B). `--synapse-iterations N` (**default 3**)
  bounds the Cortex repair budget. Project scoring feeds real sandbox build failures and incomplete
  functional gates back into additional Cortex/Synapse repair prompts before final scoring; sandbox
  infrastructure failures remain run errors and are not treated as model repair work.
  Embedding model via `GAUNTLET_VERTEX_MODEL` (default `all-MiniLM-L6-v2`; install
  `benchmark[vertex]`). Design: `agent-harness/track-p-{storefront-plan,scoring,sandbox}.md`;
  sandbox image: `benchmark/sandbox/` (Node 22 via NodeSource — the distro `nodejs` apt package is
  too old for corepack).

`ruff` clean. Deferred seams (live Track-P sandbox execution, real OCR/TTS) are tracked in
[`agent-harness/implementation-plan.md`](agent-harness/implementation-plan.md).

> Naming: `benchmark/` and the *Gauntlet* / *Sentinel* / *Forge* / *Auditor* codenames are
> proposals — rename freely.
