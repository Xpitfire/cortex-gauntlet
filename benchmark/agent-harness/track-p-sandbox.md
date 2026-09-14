# Track P — sandboxed containerized execution spec

Goal C: build, serve, and exercise an **untrusted, model-generated full-stack repository** without
risking the host. The runner is the only thing that touches the candidate code; it returns a
`SandboxResult` the scorer + report consume. A crash is data, never a suite-abort (consistent with the
TUI runner). If Docker is unavailable the track reports `skip` with a reason — never a fake pass.

## 1. Isolation model

- **Ephemeral container per candidate.** Pinned base image (e.g. `node:22-bookworm-slim` + a Python
  layer; exact toolchain is an open decision). The generated repo is copied (not bind-mounted) into a
  work dir owned by a **non-root** user (uid 1000). No host paths are mounted writable; no host env
  is passed except an injected `STRIPE_TEST_*` test key.
- **Filesystem.** Read-only root where possible; a small writable tmpfs work dir + `/tmp`; output and
  artifacts (screenshots, logs, traces) written to a mounted **read-only-from-host, write-from-
  container** artifacts dir scoped to the run.
- **Lifecycle.** Create → install phase → build phase → serve+test phase → collect artifacts →
  `docker rm -f`. Containers are always removed (even on timeout/kill); no dangling state.

## 2. Resource & time limits (fail-safe)

- CPU (`--cpus`), memory (`--memory` + `--memory-swap` equal to disable swap), `--pids-limit`,
  ulimits, and a per-phase **wall-clock timeout** (install / build / serve / each journey).
- Output caps (stdout/stderr truncated), artifact size cap, max screenshots.
- A global run budget; on any breach the container is killed and the phase recorded as failed.

## 3. Network policy (default deny-egress)

- **Install phase only:** attach to a network with egress allowed to the **package registry** (and
  nothing else) so dependencies resolve; everything else blocked.
- **Build + serve + test phases:** run on an **internal** Docker network with **no egress**. The
  only permitted outbound is the **Stripe test** endpoint via an allowlisted proxy (or a bundled
  Stripe test stub if egress must be fully closed) — real charges are impossible.
- The app binds `127.0.0.1:$PORT` inside the container; the browser reaches it on the internal net.
- Mirrors Cortex's governed-sandbox posture — prefer `cortex docker …` / policy-gated execution over
  raw daemon/socket access where the runtime provides it; fall back to the local Docker SDK with the
  same controls when running the benchmark standalone.

## 4. Browser-in-sandbox (evidence capture)

- **Playwright (chromium) runs inside the sandbox network**, driving the served PWA. It executes the
  `acceptance.json` journeys (role/name heuristics, since the app's selectors are the harness's
  choice), captures **per-screen screenshots** (home/listing/pdp/cart/checkout/confirmation) at
  mobile (390px) + desktop (1280px), plus traces and console/network logs.
- PWA/a11y: a Lighthouse-style installability check + **axe-core** injected per page.
- Screenshots are the evidence the **vision judge** scores against the reference frames, and feed the
  report's side-by-side gallery. Logs/traces attach to the run for debugging.

## 5. Tool usage

- The build phase may use a constrained toolchain inside the container (package manager, compiler,
  test runner, bundler). All execution is **capture-only** and bounded by the limits above. No tool
  can reach the host or the public network outside the install allowlist.

## 6. Runner contract

```
@dataclass SandboxResult:
    built: bool                 # install+build+boot succeeded
    served: bool                # app answered on ready_path
    journeys: list[CheckResult] # per acceptance journey/check (passed, detail, evidence ref)
    rest: list[CheckResult]     # best-effort REST contract checks
    pwa: list[CheckResult]; a11y: list[CheckResult]; robustness: list[CheckResult]
    screenshots: dict[str,str]  # screen -> artifact path (mobile+desktop)
    files: dict[str,str]        # captured repo tree (for static analysis + code judge)
    routes: list[str]           # discovered routes (input to the capability trajectory)
    logs: str; trace_ref: str | None
    timings_ms: dict[str,int]   # per phase
    error: str | None           # populated on a sandbox-level failure (→ ERROR cell, never aborts)
```

`run_sandbox(repo_files, acceptance, *, limits, artifacts_dir) -> SandboxResult`. The Track-P
adapter maps `SandboxResult` → the result object the scorer (`track-p-scoring.md`) and the report/TUI
consume, exactly like the existing generative e2e runner but containerized and full-repo.

## 7. Wiring & degradation

- New `--track project` (codename *Atelier*) reusing the suite/report/TUI plumbing; `cortex benchmark
  run --track project …` forwards through the existing passthrough.
- **Docker absent / disabled** → the track emits `skip` with a clear reason (parity with the
  TS/JS-without-node and Docker-absent paths). Optionally a reduced "static-only" mode (no serve) that
  still scores `code_health`, `code_arch`, and `vertex_arch` from the files alone.
- All execution honors the repo's docker-local-runtime policy: containerized, resource-bounded,
  egress-denied — it must not run app servers or test suites bare on the host.

## 8. Threat model (what we defend against)
- Generated code that tries to read host files, exfiltrate data, mine, or spawn unbounded processes →
  blocked by non-root + no host mounts + deny-egress + pids/cpu/mem caps + ephemeral teardown.
- Malicious dependencies → install isolated to the registry-only phase; serve/test phase has no
  egress; dependency/slopsquat + secret scans run as part of `code_health`.
- Runaway builds → per-phase timeouts + global budget + forced container removal.
