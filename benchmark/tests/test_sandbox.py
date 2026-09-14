"""Tests for the Track P sandbox pure helpers (no Docker): Dockerfile, run argv, result→Candidate."""

import pytest

from gauntlet.errors import SandboxUnavailable
from gauntlet.project import sandbox
from gauntlet.project.launch import LaunchPlan


def test_refuses_when_docker_absent(monkeypatch):
    # Track P has no host-execution fallback: an absent daemon is a refusal, not a silent None that a
    # caller could mistake for "ran and found nothing".
    monkeypatch.setattr(sandbox, "docker_available", lambda: False)
    brief = type("B", (), {"acceptance": {}})()
    # matches "Docker is unavailable; refusing project host execution" (plain substring, no regex chars)
    with pytest.raises(SandboxUnavailable, match="refusing project host execution"):
        sandbox.run_sandbox(brief, {"package.json": "{}"})


def test_candidate_dockerfile_installs_and_builds():
    plan = LaunchPlan("pnpm", ["pnpm", "install"], ["pnpm", "run", "build"], ["pnpm", "run", "preview"],
                      workdir="web")
    df = sandbox._candidate_dockerfile(plan)
    assert f"FROM {sandbox.BASE_TAG}" in df
    assert "COPY --chown=1000:1000 repo/ /work/" in df
    assert "WORKDIR /work/web" in df
    assert "RUN pnpm install" in df and "RUN pnpm run build" in df


def test_run_argv_is_hardened_and_network_isolated():
    plan = LaunchPlan("pnpm", serve=["pnpm", "run", "preview"], port=8080)
    argv = sandbox._run_argv("img", "name", __import__("pathlib").Path("/art"), plan, "/artifacts/acceptance.json")
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"  # no egress
    # Starts as root so network_guard.py can install the fail-closed firewall, then drops to uid 1000
    # inside the container; NET_ADMIN builds the rules and SETUID/SETGID shed the privilege after.
    assert argv[argv.index("--user") + 1] == "0:0"
    cap_adds = [argv[i + 1] for i, a in enumerate(argv) if a == "--cap-add"]
    assert cap_adds == ["NET_ADMIN", "SETUID", "SETGID"]
    assert "ALL" in argv  # --cap-drop ALL
    assert "no-new-privileges" in argv
    assert "--pids-limit" in argv and "--memory" in argv
    joined = " ".join(argv)
    assert "GAUNTLET_SERVE=" in joined and "/probe/probe.py" in argv
    # the guard is the entrypoint; the probe only ever runs as its `--` payload. With the default
    # no-egress policy the guard takes no --allow-host args, so it sits immediately before `--`.
    sep = argv.index("--")
    assert argv[sep - 2:sep] == ["python3", "/probe/network_guard.py"]
    assert argv[sep + 1:sep + 3] == ["python3", "/probe/probe.py"]


def test_result_maps_to_candidate_with_behaviour_capabilities():
    acceptance = {"journeys": [
        {"id": "home", "checks": [{"desc": "home page with header and cart"}]},
        {"id": "cart", "checks": [{"desc": "cart with totals"}]},
    ], "robustness": [{"id": "unknown_route"}]}
    result = {"served": True,
              "ui": {"available": True,
                     "journeys": [{"id": "home", "passed": True}, {"id": "cart", "passed": False}],
                     "screenshots": {"home": "/art/home.png"}},
              "rest": [{"id": "list_products", "desc": "products list api", "passed": True}],
              "robustness": [{"id": "unknown_route", "passed": True}]}
    plan = LaunchPlan("pnpm", note="node/pnpm")
    cand = sandbox._to_candidate("codex", True, {"server/api.ts": "x", "ui/app.tsx": "y"},
                                 acceptance, result, plan)
    assert cand.built and cand.served
    assert cand.journey_pass == {"home": True, "cart": False}
    assert "home page with header and cart" in cand.capabilities  # passed journey
    assert "products list api" in cand.capabilities  # passed REST contract
    assert "cart with totals" not in cand.capabilities  # failed journey excluded
    assert cand.screenshots == {"home": "/art/home.png"}
