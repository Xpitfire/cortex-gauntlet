"""Containerized, safe execution of an untrusted generated repo (Track P live mode).

Two phases: (1) build a per-run image FROM the sandbox base (Node 22 + pnpm + Python + Playwright +
the probe) that COPYs the candidate repo and runs install + build *with* registry egress; (2) run the
probe from that image with `--network none`, non-root, `--cap-drop ALL`, no-new-privileges, and
CPU/memory/pid/time limits — it serves the app on 127.0.0.1 and exercises it (REST + Playwright UI +
PWA/a11y + robustness), writing result.json + screenshots to a mounted artifacts dir. The host maps
that into a Candidate. Ephemeral: the candidate image is removed afterwards.

If Docker is unavailable the runner returns None → the suite records `skip` (never a fake pass). The
orchestration requires a Docker daemon (validated in a Docker-enabled env); the pure helpers
(`_candidate_dockerfile`, `_run_argv`, `_to_candidate`) are unit-tested without one.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from ..errors import SandboxUnavailable
from ..analysis import _proc
from ..bootstrap import app_files
from ..livegen.streaming import run_streamed
from . import containers
from .arch import architecture_descriptors
from .launch import LaunchPlan, discover_launch
from .models import Candidate, ProjectBrief, ProjectResult

# build_timeout_s caps the cached base image; the candidate build uses an INACTIVITY watchdog instead
# (build_inactivity_s of no log output -> stuck) so a slow-but-progressing install/compile is never cut
# off, while a hung build is killed quickly. probe_timeout_s bounds the in-container e2e (serve + probe).
LIMITS = {"cpus": "2", "memory": "2g", "pids": "256", "build_timeout_s": 1800,
          "probe_timeout_s": 600, "build_inactivity_s": 900, "build_ceiling_s": 5400}
_SANDBOX_DIR = Path(__file__).resolve().parents[2] / "sandbox"  # benchmark/sandbox (Dockerfile + probe)


def _base_tag() -> str:
    """Content-address the trusted sandbox evaluator image; stale tags must never score new code."""

    digest = hashlib.sha256()
    for path in (
        _SANDBOX_DIR / "Dockerfile",
        _SANDBOX_DIR / "network_guard.py",
        Path(__file__).with_name("probe.py"),
        Path(__file__).with_name("egress_proxy.py"),
    ):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return f"gauntlet-sandbox-base:{digest.hexdigest()[:16]}"


BASE_TAG = _base_tag()
_PROXY_HOST = "egress"  # sidecar container/alias on the private network
_PROXY_PORT = 8888


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return _proc.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _safe_write_tree(base: Path, files: dict[str, str]) -> list[str]:
    """Write `files` (UNTRUSTED model output) under `base`, REFUSING any key that escapes `base`.

    The keys are attacker-controlled, so a naive `base / rel` join lets an absolute key (`/etc/cron.d/x`)
    or a `../` key (`../../../etc/passwd`) escape the build context and write arbitrary HOST files (CWE-22).
    We reject absolute paths and any path that does not resolve INSIDE `base`, returning the rejected keys;
    safe files are written, traversal keys are skipped (never written outside the context)."""

    base = base.resolve()
    skipped: list[str] = []
    for rel, content in files.items():
        if Path(rel).is_absolute():
            skipped.append(rel)
            continue
        dest = (base / rel).resolve()
        if dest != base and not dest.is_relative_to(base):
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return skipped


def _candidate_dockerfile(launch: LaunchPlan) -> str:
    """A per-run Dockerfile: COPY the repo, then install + build (registry-egress phase)."""

    install = " ".join(launch.install) if launch.install else "true"
    build = " ".join(launch.build) if launch.build else "true"
    return (
        f"FROM {BASE_TAG}\n"
        "COPY --chown=1000:1000 repo/ /work/\n"
        f"WORKDIR /work/{launch.workdir}\n"
        f"RUN {install}\n"
        f"RUN {build}\n"
    )


def _run_argv(image: str, name: str, artifacts: Path, launch: LaunchPlan, acceptance_in_image: str,
              *, network_policy: str = "none", network_name: str = "none") -> list[str]:
    """Hardened `docker run` of the probe. Default: NO egress. `stripe-test`: only via the allowlist proxy.

    Under `stripe-test` the candidate joins a private network and routes HTTPS through the egress
    sidecar (HTTPS_PROXY), which tunnels CONNECT only to Stripe test hosts — every other destination
    is refused, so Stripe.js + test PaymentIntents work while the app has no other egress.
    """

    proxy = f"http://{_PROXY_HOST}:{_PROXY_PORT}"
    guard_args = [] if network_policy != "stripe-test" else ["--allow-host", _PROXY_HOST]
    net = network_name if network_policy == "stripe-test" else "none"
    egress_env = ([] if network_policy != "stripe-test" else
                  ["-e", f"HTTPS_PROXY={proxy}", "-e", f"HTTP_PROXY={proxy}",
                   "-e", "NO_PROXY=127.0.0.1,localhost"])
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", net,  # "none" = no egress; private net = egress only via the allowlist proxy
        "--user", "0:0", "--cap-drop", "ALL",
        "--cap-add", "NET_ADMIN", "--cap-add", "SETUID", "--cap-add", "SETGID",
        "--security-opt", "no-new-privileges",
        "--cpus", LIMITS["cpus"], "--memory", LIMITS["memory"], "--memory-swap", LIMITS["memory"],
        "--pids-limit", LIMITS["pids"], "--tmpfs", "/tmp",
        "-v", f"{artifacts}:/artifacts",
        "-e", f"GAUNTLET_SERVE={json.dumps(launch.serve)}",
        "-e", f"GAUNTLET_PORT={launch.port}",
        "-e", "GAUNTLET_READY=/", *egress_env,
        image, "python3", "/probe/network_guard.py", *guard_args, "--",
        "python3", "/probe/probe.py", f"/work/{launch.workdir}", acceptance_in_image, "/artifacts",
    ]


def _start_egress_proxy(network_name: str) -> str | None:
    """Start the allowlist CONNECT proxy dual-homed: on the candidate's internal net + the WAN bridge.

    The candidate sits on an `--internal` network (no WAN). The proxy receives its CONNECTs there and
    is also attached to the default bridge to reach Stripe — so the only egress path is the allowlist.
    """

    name = f"{_PROXY_HOST}-{network_name}"
    proc = _proc.run(
        ["docker", "run", "-d", "--rm", "--name", name, "--network", network_name,
         "--network-alias", _PROXY_HOST, "--cap-drop", "ALL",
         "--security-opt", "no-new-privileges", "--memory", "256m", "--pids-limit", "64",
         "-e", f"PROXY_PORT={_PROXY_PORT}",
         BASE_TAG, "python3", "/probe/egress_proxy.py"],
        capture_output=True, timeout=60)
    if proc.returncode != 0:
        return None
    connected = _proc.run(
        ["docker", "network", "connect", "bridge", name], capture_output=True,
    )
    if connected.returncode != 0:
        _proc.run(["docker", "rm", "-f", name], capture_output=True)
        return None
    return name


def _capabilities(acceptance: dict, result: dict) -> list[str]:
    """Behaviour-derived capability trajectory: descriptors of journeys/contracts that actually passed."""

    journeys = {j["id"]: j for j in acceptance.get("journeys", [])}
    rest_desc = {c["id"]: c.get("desc", c["id"]) for c in acceptance.get("rest_contracts", [])}
    passed_ids = [j["id"] for j in result.get("ui", {}).get("journeys", []) if j.get("passed")]
    caps = [journeys[jid]["checks"][0]["desc"] for jid in passed_ids
            if journeys.get(jid, {}).get("checks")]
    caps += [c.get("desc") or rest_desc.get(c["id"], c["id"])
             for c in result.get("rest", []) if c.get("passed")]
    return caps


def _to_candidate(harness_id: str, built: bool, repo_files: dict[str, str], acceptance: dict,
                  result: dict, launch: LaunchPlan) -> Candidate:
    ui = result.get("ui", {})
    if result.get("served") and ui.get("available") is not True:
        raise SandboxUnavailable("Required project UI evaluator is unavailable")
    score_files = app_files(repo_files)
    return Candidate(
        harness_id=harness_id, built=built, served=bool(result.get("served")),
        capabilities=_capabilities(acceptance, result),
        journey_pass={j["id"]: bool(j.get("passed")) for j in ui.get("journeys", [])},
        # default evaluable=True for legacy records that predate the field (preserves old behaviour)
        journey_eval={j["id"]: bool(j.get("evaluable", True)) for j in ui.get("journeys", [])},
        pwa_a11y={c["id"]: bool(c.get("passed")) for c in result.get("pwa_a11y", [])},
        robustness={c["id"]: bool(c.get("passed")) for c in result.get("robustness", [])},
        files=repo_files,
        # role-level descriptors (not bare dir names) so VERTEX-architecture + the CLIP judge get real signal
        module_descriptors=[launch.note, *architecture_descriptors(score_files)],
        screenshots=ui.get("screenshots", {}) or {},
    )


def _ensure_base() -> tuple[bool, str]:
    """Build the sandbox base image (cached). Stages the Dockerfile + the single-source probe.py.
    Returns (ok, error_tail) — the build log tail is surfaced on failure instead of being swallowed."""

    if _proc.run(["docker", "image", "inspect", BASE_TAG], capture_output=True).returncode == 0:
        return True, ""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Path(tmp)
        shutil.copy(_SANDBOX_DIR / "Dockerfile", ctx / "Dockerfile")
        shutil.copy(_SANDBOX_DIR / "network_guard.py", ctx / "network_guard.py")
        shutil.copy(Path(__file__).with_name("probe.py"), ctx / "probe.py")  # gauntlet/project/probe.py
        shutil.copy(Path(__file__).with_name("egress_proxy.py"), ctx / "egress_proxy.py")
        proc = _proc.run(["docker", "build", "-t", BASE_TAG, str(ctx)],
                              capture_output=True, text=True, timeout=LIMITS["build_timeout_s"])
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout or "")[-800:]


def run_sandbox(brief: ProjectBrief, repo_files: dict[str, str], *, harness_id: str = "live",
                run_dir: Path | None = None, network_policy: str = "none",
                reporter: object | None = None) -> Candidate | None:
    """Build, serve, and probe a candidate, separating evaluator outages from candidate failures.

    `network_policy="stripe-test"` routes only allowlisted Stripe test traffic through a private proxy;
    the default denies all egress.
    """

    if not docker_available():
        raise SandboxUnavailable("Docker is unavailable; refusing project host execution")
    if not repo_files:
        return None
    launch = discover_launch(repo_files)
    base_ok, base_err = _proc.retry_fd_race(_ensure_base)
    if not base_ok:
        raise SandboxUnavailable(f"sandbox base image build failed: {base_err}".strip())

    with tempfile.TemporaryDirectory() as tmp:
        ctx = Path(tmp)
        repo = ctx / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        # repo_files is UNTRUSTED model output — refuse any key that escapes the temp context (an absolute
        # or `../` key would write arbitrary HOST files before the build, defeating the sandbox; CWE-22).
        skipped = _safe_write_tree(repo, repo_files)
        if skipped:
            return Candidate(harness_id=harness_id, built=False, served=False, files=repo_files,
                             error=f"rejected unsafe paths in generated repo: {skipped[:10]}")
        (ctx / "acceptance.json").write_text(json.dumps(brief.acceptance))
        (ctx / "Dockerfile").write_text(_candidate_dockerfile(launch))
        image = f"gauntlet-cand-{uuid.uuid4().hex[:12]}"
        artifacts = (run_dir / "sandbox" / harness_id) if run_dir else (ctx / "artifacts")
        artifacts.mkdir(parents=True, exist_ok=True)

        on_line = getattr(reporter, "cli_line", None)
        on_tick = getattr(reporter, "tick", None)
        # stream the install/compile log live + kill only on inactivity (a slow npm install/tsc keeps
        # printing, so it survives; a hung build goes silent and is terminated) — never a fixed wall cap
        # retry a TRANSIENT fork/exec fd-race on the build's Popen (heavy under a busy suite — many
        # concurrent docker builds churn the fd table); a real build failure returns non-zero, not a raise
        build = _proc.retry_fd_race(lambda: run_streamed(
            ["docker", "build", "-t", image, str(ctx)],
            inactivity_s=LIMITS["build_inactivity_s"], ceiling_s=LIMITS["build_ceiling_s"],
            on_output=on_line, on_tick=on_tick))
        built = build.returncode == 0 and not (build.stuck or build.exceeded)
        # surface the candidate install/build failure instead of swallowing it (a 0-score otherwise
        # looks like a scoring bug rather than a broken `npm install`/`tsc` in the generated repo)
        stuck_note = (" (build went silent — terminated as stuck)" if build.stuck else
                      " (build exceeded the safety ceiling)" if build.exceeded else "")
        build_error = "" if built else (
            f"candidate build failed{stuck_note}: {(build.stderr or build.stdout or '')[-800:]}")
        docker_error = (build.stderr or build.stdout or "").lower()
        if not built and any(
            marker in docker_error
            for marker in ("cannot connect to the docker daemon", "error during connect",
                           "is the docker daemon running")
        ):
            raise SandboxUnavailable("Docker failed during candidate build")
        result: dict = {}
        network_name, proxy = "none", None
        if built and launch.serveable:
            # acceptance.json travels via the mounted artifacts dir → /artifacts/acceptance.json
            shutil.copy(ctx / "acceptance.json", artifacts / "acceptance.json")
            if network_policy == "stripe-test":
                network_name = f"gauntlet-net-{image}"
                net = _proc.run(
                    ["docker", "network", "create", "--internal", network_name],
                    capture_output=True,
                )
                if net.returncode != 0:
                    _proc.run(["docker", "image", "rm", "-f", image], capture_output=True)
                    raise SandboxUnavailable("sandbox network creation failed")
                proxy = _start_egress_proxy(network_name)
                if proxy is None:
                    _proc.run(["docker", "network", "rm", network_name], capture_output=True)
                    _proc.run(["docker", "image", "rm", "-f", image], capture_output=True)
                    raise SandboxUnavailable("sandbox egress proxy failed to start")
            argv = _run_argv(image, image, artifacts, launch, "/artifacts/acceptance.json",
                             network_policy=network_policy, network_name=network_name)
            try:
                probe = _proc.run(
                    argv, capture_output=True, timeout=LIMITS["probe_timeout_s"], check=False,
                )
                result_path = artifacts / "result.json"
                if probe.returncode in (125, 126, 127) or not result_path.exists():
                    _proc.run(["docker", "image", "rm", "-f", image], capture_output=True)
                    raise SandboxUnavailable("sandbox probe produced no evaluator result")
                result = json.loads(result_path.read_text())
            except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
                _proc.run(["docker", "image", "rm", "-f", image], capture_output=True)
                raise SandboxUnavailable(f"sandbox probe failed: {type(exc).__name__}") from exc
            finally:
                if proxy:
                    _proc.run(["docker", "rm", "-f", proxy], capture_output=True)
                if network_name != "none":
                    _proc.run(["docker", "network", "rm", network_name], capture_output=True)
        # optional: keep a plainly-served copy alive on its own host port for qualitative review (the
        # SCORE still came from the hardened no-egress probe above). Torn down when the TUI closes.
        kept = (containers.start(image, harness_id, launch, run_dir)
                if (built and launch.serveable and run_dir is not None and containers.keep_enabled())
                else None)
        if kept is not None:
            if on_line:
                on_line(f"▸ kept alive for review: {kept['url']}")
        else:
            _proc.run(["docker", "image", "rm", "-f", image], capture_output=True)  # ephemeral

    candidate = _to_candidate(harness_id, built, repo_files, brief.acceptance, result, launch)
    # the probe records CONTAINER paths (/artifacts/<screen>.png); map them to the mounted host
    # artifacts dir so the vision judges — which score BEFORE bundle_app_shots web-bundles the winner —
    # can actually read the files (otherwise visual/ux silently zero on every live run).
    if run_dir is not None and candidate.screenshots:
        candidate.screenshots = host_screenshots(candidate.screenshots,
                                                 run_dir / "sandbox" / harness_id)
    if build_error:  # build never ran the probe — record why so the 0-score is explainable
        candidate.error = build_error
    return candidate


def host_screenshots(screenshots: dict[str, str], shots_dir: Path) -> dict[str, str]:
    """Map the probe's recorded container screenshot paths to the mounted host artifacts dir; a path
    with no host copy is kept as recorded (the judges skip it, exactly as before)."""

    out: dict[str, str] = {}
    for screen, path in screenshots.items():
        host = shots_dir / Path(path).name
        out[screen] = str(host) if host.exists() else path
    return out


def bundle_app_shots(cand, run_dir: Path | None) -> None:
    """Copy the sandbox's captured app PNGs (run_dir/sandbox/<harness>/<screen>.png) into the run's
    web-bundled assets/ and rewrite the Candidate's screenshot paths to run-relative ones, so the
    report renders the real renders. The raw container paths (/artifacts/*.png) are not web-resolvable."""

    if run_dir is None or not cand.screenshots:
        return
    src_dir = Path(run_dir) / "sandbox" / cand.harness_id
    assets = Path(run_dir) / "assets"
    rewritten: dict[str, str] = {}
    for screen, path in cand.screenshots.items():
        src = src_dir / Path(path).name
        if src.exists():
            assets.mkdir(parents=True, exist_ok=True)
            dst_name = f"{cand.harness_id}-{src.name}"
            shutil.copy(src, assets / dst_name)
            rewritten[screen] = f"assets/{dst_name}"
    cand.screenshots = rewritten


def score_passes(brief: ProjectBrief, snapshots: list[dict[str, str]], *, harness_id: str,
                 run_dir: Path | None, network_policy: str, judges, reporter: object | None = None,
                 vertex_ref: str | None = None):
    """Sandbox + score the pass snapshots and return the BEST-composite ProjectResult, with the winner
    promoted to the canonical sandbox/<harness> dir + assets.

    Docker-cost bound: with more than two snapshots only the FIRST (the floor, ≈ the raw single-shot)
    and the LAST (final cumulative repo) are sandboxed — middle passes are skipped, so the argmax is
    over {floor, final} plus any later repair iterations, not literally every pass.

    Synapse repairs chase spec markers, which do NOT track real functionality — a marker-improving repair
    can ship a LESS functional repo. Best-of guarantees the shipped score is never worse than the floor
    pass; since pass 1 ≈ the raw single-shot, the Synapse-wrapped arm is never worse than the raw arm.
    Raw arms pass a single snapshot, so this is byte-identical to the old single-sandbox path for them."""

    from ..analysis import _proc
    from .score import score_project

    snaps = snapshots or [{}]
    if len(snaps) > 2:  # bound the docker cost / fork pressure: the floor (pass 1 ≈ raw) and the final
        snaps = [snaps[0], snaps[-1]]  # cumulative repo decide the best-of; Cortex ≥ raw still holds
    multi = len(snaps) > 1
    best: tuple[ProjectResult, Candidate, dict[str, str]] | None = None
    for idx, snap in enumerate(snaps):
        hid = f"{harness_id}__p{idx}" if multi else harness_id  # per-pass artifacts; winner promoted below
        if reporter is not None and multi:
            getattr(reporter, "phase", lambda *_: None)(
                f"Sandbox · best-of pass {idx + 1}/{len(snaps)} ({len(snap)} files)")
        cand = run_sandbox(
            brief, snap, harness_id=hid, run_dir=run_dir,
            network_policy=network_policy, reporter=reporter,
        )
        if cand is None:
            raise SandboxUnavailable("candidate produced no files for sandbox execution")
        result = _proc.retry_fd_race(
            lambda c=cand: score_project(
                brief, c, judges, sandbox_backend="docker", vertex_ref=vertex_ref,
            )
        )
        if best is None or result.signals.composite > best[0].signals.composite:
            best = (result, cand, snap)
    result, cand, snap = best  # type: ignore[misc]
    result.harness_id = cand.harness_id = harness_id  # aggregate under the real arm id, not the pass id
    result.files = snap
    bundle_app_shots(cand, run_dir)
    result.screenshots = cand.screenshots
    if run_dir is not None and snap:  # promote the winning repo to the canonical viewer path
        canon = Path(run_dir) / "sandbox" / harness_id / "repo"
        canon.mkdir(parents=True, exist_ok=True)
        _safe_write_tree(canon, snap)
    return result
