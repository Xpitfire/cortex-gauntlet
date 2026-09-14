# BENCHMARK — index & run adapter

Entry point for driving the Cortex Harness Benchmark (Gauntlet). Phase 1 defines the contract;
the `cortex benchmark` CLI lands in M1/M8 (see `agent-harness/implementation-plan.md`).

## Read order

1. `README.md` — what & why, map, non-negotiables.
2. `agent-harness/research-state-of-art.md` — SOTA grounding + citations.
3. `agent-harness/requirements.md` — requirements checklist.
4. `agent-harness/architecture.md` — components & data flow.
5. `docs/dimensions.md` · `docs/attack-taxonomy.md` · `docs/scoring-and-judging.md` ·
   `docs/reporting-design.md` · `docs/reuse-map.md`.
6. `agent-harness/{implementation-plan,security-model,acceptance-tests}.md`.

## Running the M1 slice (works today, zero-dep)

The Track S vertical slice runs offline with the bundled mock harnesses:

```
# from the repo root (uses the project venv; benchmark/ on PYTHONPATH)
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet run
# → results/<run-id>/runrecord.json + report.html   (open report.html in a browser)

# live harnesses / judge via the Cortex CLI:
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet run \
    --adapters cortex:codex,cortex:claude --judge cortex

# rebuild a report from a saved record:
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet report <run-id>

# tests + lint — benchmark is its own uv project, so run these from benchmark/.
cd benchmark

# one-time setup. `uv sync` installs the dev group (pytest, the [tui]/[analysis] extras, ruff/mypy,
# playwright, plus the sibling synapse-library and the parent cortex-cli that gauntlet imports).
# The playwright wheel ships no browser binary and uv cannot fetch one, so install it explicitly:
# without it the Track P/G UI checks degrade to a stated failure ("no browser: playwright or
# chromium unavailable") instead of erroring, and the UI assertions cannot pass.
uv sync
uv run playwright install chromium

uv run pytest tests -q
uv run ruff check gauntlet tests --config ../ruff.toml

# the Track P/G sandbox tests additionally need a Docker daemon that can build the base image
# (sandbox/Dockerfile); without it they raise SandboxUnavailable rather than falling back to the host.
```

## Public results site & (re)deploy

Live, public (no login): **https://benchmark.cortex.a2olabs.com/** — the benchmark
landing page, paper, and interactive run reports. Control it from the CLI:

```
# 0. or run ALL tracks in one command (per-track seeds baked in) + build the site:
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet suite          # mock; add --live --provider … --tui

# 1. run the tracks you want individually (writes results/<run-id>/)
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet run --track security
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet run --track quality
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet run --track generative

# 2. rebuild the aggregated public site from every results/ run -> benchmark/site/public/
PYTHONPATH=benchmark .venv/bin/python3 -m gauntlet site

# 3. explicitly stage screened reports: the repo's runs/ ignore skips new runs.
git add -f -- benchmark/site/public/runs

# 4. review, commit/push the canonical sources and generated site, then deploy
#    the dedicated benchmark manifest. The default manifest belongs to Dentate.
cortex --profile <your-production-profile> deploy --manifest .cortex/benchmark.app.yml --ref <published-commit> --dry-run
cortex --profile <your-production-profile> deploy --manifest .cortex/benchmark.app.yml --ref <published-commit>
cortex --profile <your-production-profile> jobs watch <job-id>
```

Deploy config: `.cortex/benchmark.app.yml` selects only workspace `benchmark`,
service `site`, and root `docker-compose.benchmark.yml`. It builds `benchmark/site/`
(nginx serving `public/`) and declares the public benchmark URL. Use an explicitly
authenticated production profile; never use bare `cortex deploy` from this repo.
Pass the exact pushed commit SHA to `--ref`, not the moving `main` branch.
The versioned deployment must publish committed artifacts rather than hand-editing
the running container. Roll back only to a previously screened Git ref through
the same manifest with `--ref <previous-ref>`. Do not restore known-exposed artifacts;
release 0.1.4 is not a safe rollback target.

The public navigation separates **Overview**, **Security**, **Quality**,
**Generative**, **Project**, **Bugfix**, **Results**, then **Paper**. Overview is
the visual entry point; each category keeps its original interactive plots,
explorers, galleries and exports, plus searchable dataset and experiment cards.
Source tabs distinguish modeled references from captured historical outputs.
Paper content and figures are independent of this presentation layer.

All five tracks and every retained run are available through **Results**, including
historical/noncompetitive records. Publication does not qualify a run for headline
comparisons. Credential/private-account indicators produce a disclosed quantitative
view: recorded results remain public while captured text, generated files and media
are withheld. Do not restore those files when publishing the restricted reports.

The primary historical package is curated in `site/results-package.json`, not
selected from the newest run timestamp. Complete modeled references and captured
historical outputs are separate collections; original/rescored alternatives retain
their own source IDs, scoring history and model labels. Selection uses coverage
and recorded seed budget, never favorable scores. No cross-source overall score
or pooled experiment is manufactured.

The Results page (`results.html`) exports `results-package.json` and `results-package.csv` with
per-harness measurements and raw-source SHA256 provenance. CSV values retain their
stored 0–1 units; the UI displays percentages. All archived reports remain linked,
including diagnostics that are not primary package sources. Rebuilding the public
package requires its selected raw records and fails explicitly if one is missing.
For a standalone diagnostic without the historical archive, use `--no-site` and
the individual report command instead of replacing the public package.
Declared evaluator/model, recorded score evaluators/instruments and rescore ancestry
are exported separately; an evaluator requested in configuration is not proof it ran.
Security utility additionally carries a per-harness evidence status. `modeled`
identifies synthetic marker measurements; `unverified` identifies historical
marker flags without a carrier-task completion validator; `unavailable` covers
missing measurements or empty denominators. Recorded rates and flags are not
rewritten. Package CSV includes `measurement_status` and `measurement_note`;
per-case Security CSV includes `utility_measurement_status`, with missing flags
remaining unavailable even when other rows for that harness are unverified.

## Planned CLI (M8 — folded into `cortex benchmark`)

```
cortex benchmark run     --track {security|generative|quality} --suite <name> \
                         --harness {claude_code|codex_cli|codex_cloud|raw_api|cortex_wrapped} \
                         --seeds 3
cortex benchmark judge   <run-id>            # (re)run LLM-as-judge scoring
cortex benchmark report  <run-id>            # → results/<run-id>/report.{html,pdf,csv}
cortex benchmark compare <run-id-a> <run-id-b>   # harness-delta view
```

Reuses `src/cortex_cli/{http,config}.py` and `cortex agent ask/run` as the judge/agent backend.

## Directory contract

- `suites/<track>/` — Case definitions + manifests (+ `vendor/<source>/PROVENANCE.md`).
- `adapters/` — harness runners implementing the Inspect Solver interface.
- `schemas/` — JSON Schemas; every RunRecord validates here.
- `results/<run-id>/` — RunRecord JSON + artifacts + generated report (git-ignored).

## Containment reminder

Live Track S currently isolates configuration, **not the agent process or host network**.
Permission-bypass CLI modes can execute actions. Decoys and modeled L1 outcomes do not
establish confinement. Do not run adversarial live agents without an independently
verified outer sandbox. See `docs/scoring-and-judging.md` for the scientific audit and
remaining evaluator-integrity blockers. Offline mock runs are synthetic, not measurements.
