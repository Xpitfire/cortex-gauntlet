"""Tests for the Stripe-test egress allowlist proxy matcher + the sandbox network_policy argv branch."""

from pathlib import Path

from gauntlet.project import sandbox
from gauntlet.project.egress_proxy import STRIPE_TEST_HOSTS, host_allowed
from gauntlet.project.launch import LaunchPlan


def test_allowlist_permits_only_stripe_test_hosts():
    assert host_allowed("js.stripe.com", STRIPE_TEST_HOSTS)
    assert host_allowed("api.stripe.com:443", STRIPE_TEST_HOSTS)  # port stripped
    assert host_allowed("edge.api.stripe.com", STRIPE_TEST_HOSTS)  # dotted-suffix
    assert not host_allowed("evil-stripe.com", STRIPE_TEST_HOSTS)  # not a dotted suffix
    assert not host_allowed("notapi.stripe.com", STRIPE_TEST_HOSTS)
    assert not host_allowed("example.com", STRIPE_TEST_HOSTS)


def test_default_policy_has_no_egress():
    plan = LaunchPlan("pnpm", serve=["pnpm", "run", "preview"], port=8080)
    argv = sandbox._run_argv("img", "name", Path("/art"), plan, "/artifacts/acceptance.json")
    assert argv[argv.index("--network") + 1] == "none"
    assert "HTTPS_PROXY" not in " ".join(argv)


def test_stripe_test_policy_routes_through_proxy():
    plan = LaunchPlan("pnpm", serve=["pnpm", "run", "preview"], port=8080)
    argv = sandbox._run_argv("img", "name", Path("/art"), plan, "/artifacts/acceptance.json",
                             network_policy="stripe-test", network_name="gauntlet-net-img")
    assert argv[argv.index("--network") + 1] == "gauntlet-net-img"  # private net, not "none"
    joined = " ".join(argv)
    assert f"HTTPS_PROXY=http://{sandbox._PROXY_HOST}:{sandbox._PROXY_PORT}" in joined
    assert "NO_PROXY=127.0.0.1,localhost" in joined  # localhost (the served app) bypasses the proxy
