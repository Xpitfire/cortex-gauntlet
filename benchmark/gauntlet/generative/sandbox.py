"""Containerized, safe execution of an UNTRUSTED generated app (Track G live mode).

`generative/e2e.py:run_e2e` historically built + served the generated app ON THE HOST (its own docstring
admits this is unsafe — untrusted model output belongs in a sandbox). This module Dockerizes it, reusing
the Track P sandbox infra (`project/sandbox.py`): a per-run image FROM the cached base COPYs the repo and
runs install + build; then the gen-probe container serves the app on 127.0.0.1 and exercises it on an
INTERNAL docker network whose ONLY other member is a stub-SLM sidecar — so the candidate has ZERO host/WAN
egress and can reach only the stub. The probe writes result.json + a screenshot into a mounted artifacts
dir; the host maps that into the SAME `E2EReport` `run_e2e` returns, so the caller is unchanged.

If Docker or sandbox infrastructure is unavailable, the caller must mark the result unevaluable. There
is no host-execution fallback for generated code.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from ..project.launch import LaunchPlan, discover_launch
from ..project.sandbox import (
    BASE_TAG,
    LIMITS,
    _candidate_dockerfile,
    _ensure_base,
    docker_available,
)
from .e2e import CheckResult, E2EReport

_SLM_ALIAS = "slm"  # the stub-SLM's network-alias on the internal net; the candidate reaches it here
_SLM_PORT = 8000
_GEN_PROBE = Path(__file__).with_name("gen_probe.py")
_STUB_SLM = Path(__file__).with_name("stub_slm.py")


def safe_write_tree(base: Path, files: dict[str, str]) -> list[str]:
    """Write `files` (UNTRUSTED model output) under `base`, REFUSING any path that escapes `base`.

    The `files` keys are attacker-controlled (a model's generated repo). A naive `base / rel` join lets an
    absolute key (`/etc/cron.d/evil`) or a `../` key (`../../../etc/passwd`) escape the build context and
    write arbitrary HOST files (CWE-22 path traversal). That defeats the very host-isolation the Docker
    sandbox exists for, and is reachable on the host build-context write AND the host fallback write. So we
    reject absolute paths and any path that does not resolve INSIDE `base`, returning the rejected keys so
    the caller can surface them. Files that pass the guard are written; traversal keys are skipped (never
    written outside the context)."""

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


def _gen_candidate_dockerfile(launch: LaunchPlan) -> str:
    """Per-run Dockerfile: FROM the base, COPY the repo, then install + build (registry-egress phase).

    Reuses the Track P `_candidate_dockerfile` (FROM BASE_TAG, COPY repo, WORKDIR, RUN install, RUN build) —
    `discover_launch` yields install/build=[] for a python brief (→ `true`) and pnpm/npm install + build for
    a node brief, so a node candidate genuinely installs + builds while a python one is a no-op."""

    return _candidate_dockerfile(launch)


def _gen_probe_argv(image: str, name: str, artifacts: Path, manifest_path: Path, gen_probe_path: Path,
                    slm_alias: str, slm_port: int, port: int, serve: list[str], network: str) -> list[str]:
    """Hardened `docker run` of the gen-probe on the INTERNAL network (pure → asserted in tests).

    The trusted entrypoint installs a fail-closed OUTPUT firewall, allowing only the stub sidecar, then
    drops permanently to uid/gid 1000 before the generated app or probe starts.

    """
    base_url = f"http://{slm_alias}:{slm_port}/v1"
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", network,  # the INTERNAL net (no host/WAN route); only the stub-SLM is reachable
        "--user", "0:0", "--cap-drop", "ALL",
        "--cap-add", "NET_ADMIN", "--cap-add", "SETUID", "--cap-add", "SETGID",
        "--security-opt", "no-new-privileges",
        "--cpus", LIMITS["cpus"], "--memory", LIMITS["memory"], "--memory-swap", LIMITS["memory"],
        "--pids-limit", LIMITS["pids"], "--tmpfs", "/tmp",
        "-v", f"{artifacts}:/artifacts",
        "-v", f"{gen_probe_path}:/probe/gen_probe.py:ro",
        "-v", f"{manifest_path}:/probe/manifest.json:ro",
        "-e", f"GAUNTLET_SERVE={json.dumps(serve)}",
        "-e", f"GAUNTLET_PORT={port}",
        "-e", "GAUNTLET_READY=/",
        "-e", "GAUNTLET_MANIFEST=/probe/manifest.json",
        "-e", f"LLM_BASE_URL={base_url}", "-e", "LLM_MODEL=stub", "-e", f"PORT={port}",
        image, "python3", "/probe/network_guard.py", "--allow-host", slm_alias, "--",
        "python3", "/probe/gen_probe.py",
    ]


def _stub_slm_argv(name: str, network: str, alias: str, port: int, stub_path: Path) -> list[str]:
    """Detached, hardened `docker run -d` of the stub-SLM sidecar on the internal net (pure → tested).

    A network-alias lets the candidate reach it by name. Hardened like the egress proxy (cap-drop ALL,
    no-new-privileges, memory/pids limits). Mounts stub_slm.py read-only and runs it on $PORT."""

    return [
        "docker", "run", "-d", "--rm", "--name", name,
        "--network", network, "--network-alias", alias,
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "256m", "--memory-swap", "256m", "--pids-limit", "64",  # no swap, like the probe
        "-v", f"{stub_path}:/probe/stub_slm.py:ro",
        "-e", f"PORT={port}",
        BASE_TAG, "python3", "/probe/stub_slm.py",
    ]


def _to_report(built: bool, result: dict, output: str = "") -> E2EReport:
    """Map the probe's result.json into the SAME E2EReport run_e2e returns (caller is unchanged)."""

    checks = [
        CheckResult(c.get("id", ""), c.get("kind", ""), bool(c.get("passed")), c.get("detail", ""))
        for c in result.get("checks", [])
    ]
    shot = result.get("screenshot")
    return E2EReport(built=built, served=bool(result.get("served")), checks=checks,
                     screenshot=f"assets/{shot}" if shot else None,
                     output=output or result.get("error", ""))


def run_generative_sandbox(manifest: dict, files: dict[str, str], harness_id: str,
                           run_dir: Path | None = None) -> E2EReport | None:
    """Build, serve, and probe the generated app inside the sealed Docker boundary.

    Candidate failures stay ordinary failed reports. Evaluator failures are distinguished through
    `infrastructure_error` so callers cannot score them as candidate failures."""

    if not docker_available():
        return None
    if not files:
        return E2EReport(built=False, served=False, output="no generated files")
    launch = discover_launch(files)
    base_ok, base_err = _ensure_base()
    if not base_ok:
        return E2EReport(built=False, served=False, infrastructure_error=f"sandbox base build failed: {base_err}".strip())

    network = sidecar = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = Path(tmp)
            repo = ctx / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            # files are UNTRUSTED model output — refuse any key that escapes the temp context (path
            # traversal would write arbitrary HOST files before the build, defeating the sandbox).
            skipped = safe_write_tree(repo, files)
            if skipped:
                return E2EReport(built=False, served=False,
                                 output=f"rejected unsafe paths in generated repo: {skipped[:10]}")
            (ctx / "Dockerfile").write_text(_gen_candidate_dockerfile(launch))
            (ctx / "manifest.json").write_text(json.dumps(manifest))
            # collision-resistant per-run name (a hash mod N could collide across runs and let one run's
            # finally remove another run's image/network/sidecar)
            image = f"gauntlet-gen-{uuid.uuid4().hex[:12]}"
            artifacts = (run_dir / "gen-sandbox" / harness_id) if run_dir else (ctx / "artifacts")
            artifacts.mkdir(parents=True, exist_ok=True)

            build = subprocess.run(["docker", "build", "-t", image, str(ctx)],
                                   capture_output=True, text=True, timeout=LIMITS["build_timeout_s"])
            built = build.returncode == 0
            if not built:
                return _to_report(False, {},
                                  output=f"candidate build failed: {(build.stderr or build.stdout or '')[-800:]}")
            if not launch.serveable:
                subprocess.run(["docker", "image", "rm", "-f", image], capture_output=True)
                return _to_report(True, {"served": False}, output="no serve command discovered")

            try:
                network = f"gauntlet-gen-net-{image}"
                # --internal: no host/WAN route at all — the candidate's ONLY peer is the stub-SLM sidecar
                net = subprocess.run(["docker", "network", "create", "--internal", network],
                                     capture_output=True, text=True)
                if net.returncode != 0:
                    network = None
                    error = f"sandbox network create failed: {(net.stderr or net.stdout or '')[-300:]}"
                    return E2EReport(built=True, served=False, infrastructure_error=error)
                sidecar = f"{_SLM_ALIAS}-{image}"
                stub = subprocess.run(_stub_slm_argv(sidecar, network, _SLM_ALIAS, _SLM_PORT, _STUB_SLM),
                                      capture_output=True, text=True, timeout=60)
                if stub.returncode != 0:
                    error = f"stub-SLM sidecar failed to start: {(stub.stderr or stub.stdout or '')[-300:]}"
                    return E2EReport(built=True, served=False, infrastructure_error=error)
                # Drive serve from the manifest's `start` (python briefs carry ["{python}","app.py","{port}"],
                # so the app gets the port the probe will probe) and fall back to discover_launch().serve only
                # when the manifest declares no start (the node brief: `npm run start` reads PORT from env).
                # gen_probe substitutes {python}/{port}; we keep {python} so it resolves in-container.
                serve = manifest.get("start") or launch.serve
                argv = _gen_probe_argv(image, image, artifacts, ctx / "manifest.json", _GEN_PROBE,
                                       _SLM_ALIAS, _SLM_PORT, launch.port, serve, network)
                probe = subprocess.run(
                    argv, capture_output=True, timeout=LIMITS["probe_timeout_s"], check=False,
                )
                result_path = artifacts / "result.json"
                if probe.returncode in (125, 126, 127) or not result_path.exists():
                    error = (probe.stderr or probe.stdout or b"sandbox probe produced no result")[-400:]
                    return E2EReport(
                        built=True, served=False,
                        infrastructure_error=error.decode(errors="replace"),
                    )
                return _to_report(True, json.loads(result_path.read_text()))
            except (subprocess.SubprocessError, OSError) as exc:
                return E2EReport(built=True, served=False, infrastructure_error=str(exc)[:200])
            finally:
                subprocess.run(["docker", "image", "rm", "-f", image], capture_output=True)  # ephemeral
    except (subprocess.SubprocessError, OSError) as exc:
        return E2EReport(built=False, served=False, infrastructure_error=str(exc)[:200])
    finally:
        if sidecar:
            subprocess.run(["docker", "rm", "-f", sidecar], capture_output=True)
        if network:
            subprocess.run(["docker", "network", "rm", network], capture_output=True)
