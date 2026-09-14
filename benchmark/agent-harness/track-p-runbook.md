# Track P — P6 live end-to-end runbook

Operator guide for running the **storefront full-repo build** (Track P, codename Atelier) live: a real
harness generates the repo, the Docker sandbox builds + serves + exercises it, and the multi-signal
scorer (objective + VERTEX + Semgrep security + Claude-vision judges) produces a report. Everything
runs ephemerally, non-root, deny-egress; the Stripe-test journey is the only permitted outbound.

This complements the design specs (`track-p-sandbox.md`, `track-p-scoring.md`,
`track-p-storefront-plan.md`) — it is the *how to actually run it* checklist.

## 0. Preconditions

- **Docker daemon** reachable (`docker info` returns 0). Without it the track records `skip`, never a
  fake pass. Prefer `cortex docker …` where the runtime provides it; fall back to local Docker with
  the same controls when running standalone.
- **~6 GB free disk** for the base image (Playwright chromium + Node 22 + pnpm + Python).
- **Harness CLIs authenticated** for whichever providers you run (`codex`, `cortex`, `cortex:claude`,
  `opencode`). Live generation needs their auth; the benchmark passes no host secrets into the sandbox.
- **Embedding model** (VERTEX): `all-MiniLM-L6-v2` downloads on first use (~90 MB), or set
  `GAUNTLET_VERTEX_MODEL=none` for the deterministic hashing fallback (CI/offline).
- **VERTEX reference mode**: configured by `--vertex-ref`. `auto` uses reference-free VERTEX-QE for
  live Project/rescore runs and the authored reference for mock fixtures. Force
  `authored|brief|repo|qe|consensus` only when running an ablation.
- **CLIP** (optional, only for `--vision-judge clip`): `sentence-transformers` + `torch` + `Pillow`
  (the `clip-ViT-B-32` model, ~340 MB, downloads on first use). Absent → `--vision-judge clip` exits
  with a clear error; it never silently downgrades. The same model can serve VERTEX
  (`GAUNTLET_VERTEX_MODEL=clip-ViT-B-32`).
- **Stripe test key** (only if running `--network-policy stripe-test`): export the publishable/secret
  **test** keys the harness brief expects via env; never a live key, never committed.

## 1. Build the sandbox base image (one-off, cached)

The runner builds it automatically on first live run; to pre-build/inspect:

```
docker build -t gauntlet-sandbox-base benchmark/sandbox
```

It stages `probe.py` (in-container harness) and `egress_proxy.py` (allowlist proxy) into `/probe/`.

## 2. Smoke test WITHOUT Docker (fastest signal)

Validates the launch→serve→probe→result→Candidate→score chain against a real local app (no container,
no browser — `run_ui` degrades to unavailable):

```
cd benchmark && PYTHONPATH=. python3 -m pytest tests/test_e2e_probe.py -q
```

Green here means the probe, REST discovery, robustness checks, and scoring are wired correctly; only
the Docker isolation + Playwright UI remain to validate in-container.

## 3. Live run — deny all egress (default)

```
# one provider, full single-brief build, Docker-sandboxed, deny-egress
gauntlet run --track project --live --provider codex
# or via the Cortex CLI passthrough
cortex benchmark run --track project --live --provider codex
```

Multiple providers (one cell each) for a head-to-head:

```
gauntlet run --track project --live --provider codex,cortex,cortex:claude
```

Artifacts land in `benchmark/results/<run-id>/`:
`runrecord.json`, `report.html`, `screenshots/` (reference frames), and
`sandbox/<harness>/` (probe `result.json`, captured screenshots, and the persisted `repo/` tree).

## 4. Live run — Stripe test egress (payment journey)

`--network-policy stripe-test` puts the candidate on an `--internal` network (no WAN) and routes its
HTTPS through the `egress_proxy.py` sidecar, which **only** tunnels CONNECT to Stripe test hosts
(`js.stripe.com`, `api.stripe.com`, `m.stripe.com`, `checkout.stripe.com`) — every other destination
is refused. The proxy is dual-homed (internal net + bridge); the candidate has no other route out.

```
gauntlet run --track project --live --provider codex --network-policy stripe-test \
  --vision-judge clip --vertex-ref auto
```

Stripe is **test mode only** — no real charges are possible; keep keys in env, out of the repo.

## 5. Live run in the IDE (TUI) with a browsable workspace

```
gauntlet tui --track project --live --provider codex --network-policy stripe-test \
  --vision-judge clip --vertex-ref auto
```

The IDE shows per-harness progress; selecting a cell opens the **full generated repo tree** (sorted by
path so folders cluster) in the syntax-highlighted editor. The same repo is persisted to
`results/tui-<run-id>/sandbox/<harness>/repo/` so it is explorable on disk afterwards. Load a past run
read-only with `gauntlet tui --track project --load <run-dir>`.

## 6. Scoring signals (what the composite is built from)

Build-gated weighted composite (weights sum to 1.0):
`functional .26 · visual .16 · vertex .14 · code_arch .12 · pwa_a11y .09 · security .09 ·
robustness .08 · code_health .06`.

- **security** — `scan_repo` runs **Semgrep** (`p/security-audit`, `p/secrets`) when the CLI is
  present, else the offline ruleset + Bandit; `security_score` is severity-weighted
  (CRITICAL 1.0 / HIGH .6 / MEDIUM .3 / LOW .1). The same scan feeds `code_health`.
- **vertex** — capability + architecture trajectory cross-similarity vs the configured reference,
  baseline-normalized. `--vertex-ref auto` resolves to `qe` for live Project/rescore and `authored`
  for mock. Embedding via `all-MiniLM-L6-v2`, `GAUNTLET_VERTEX_MODEL=none` (hashing), or
  `GAUNTLET_VERTEX_MODEL=clip-ViT-B-32` to share the CLIP model used by the vision judge.
- **visual / code_arch / ux** — the qualitative judge, gated on the app actually serving. The backend
  is an **explicit choice** via `--vision-judge` and the backend that actually ran is recorded on
  every result (`signals.detail.judge_backend`) and in the run methodology — never silently swapped:
  - `heuristic` (default) — deterministic, bounded proxies from the objective observation; labelled
    `heuristic-proxy`. The offline/mock backend. Honest stand-ins, **not** LLM verdicts.
  - `clip` — a local CLIP vision-language model (sentence-transformers, no API): visual = CLIP
    image–image cosine(render, reference frame); ux = image-set journey coverage; code_arch =
    semantic match of the realized module structure to the reference architecture. Requires `--live`.
  - `claude-vision` — rubric LLM judge via the `claude` CLI. Requires `--live` + an authenticated CLI;
    if the CLI is absent the run **fails loudly** (it never downgrades to a heuristic while claiming
    `claude-vision`). A judge that cannot produce a verdict raises rather than recording a fake 0.

  `clip`/`claude-vision` need `--live` (they require real screenshots); requesting them in mock mode
  exits with a clear error. `--basis` in the report shows whether a delta is `measured` (live) or
  `mock (modelled)` so the headline "Cortex advantage" is never mistaken for a measured result.

## 7. Safety invariants (do not regress)

- Untrusted repo executes **only** in the ephemeral, non-root (`--user 1000`), `--cap-drop ALL`,
  `--security-opt no-new-privileges`, CPU/mem/pid/time-limited container — never on the host.
- Default egress is **none**; `stripe-test` is the only widened policy and is allowlist-enforced.
- Containers + the candidate image + the proxy + the private network are always torn down, even on
  timeout/kill. A sandbox crash is recorded as an `ERROR`/`skip` cell — it never aborts the suite.
- No host secrets enter the sandbox except an injected Stripe **test** key when that policy is on.
