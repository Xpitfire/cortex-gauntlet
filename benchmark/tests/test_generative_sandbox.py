"""Track G live Dockerization: the generative app is built/served/probed in a Docker sandbox.

Hermetic — NO real Docker daemon, network, model, or npm/pnpm:
- The PURE builders (candidate Dockerfile, gen-probe argv, stub-SLM argv) are asserted with NO Docker:
  the Dockerfile FROMs the base + COPYs the repo + runs install/build; the probe argv is hardened
  (root + a minimal capability set so the entrypoint can install the firewall then drop to uid 1000,
  cap-drop ALL, no-new-privileges, the INTERNAL net not the default bridge), mounts the
  probe + manifest read-only, points LLM_BASE_URL at the stub alias, and runs gen_probe.py; the stub
  argv uses a network-alias and is hardened.
- With docker_available() monkeypatched False, run_live_brief REFUSES: Track G has no host-execution
  fallback for generated code, so both a python and a node/TS brief raise SandboxUnavailable before
  anything is generated, written, or served.
- The gen_probe check functions are exercised against in-process stub servers (rest/chat/ui-degraded).
- stub_slm answers with the OpenAI choices shape.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from gauntlet.errors import SandboxUnavailable
from gauntlet.generative import gen_probe, live, sandbox, stub_slm
from gauntlet.generative.judge import HeuristicGenerativeJudge
from gauntlet.generative.live import live_briefs, run_live_brief
from gauntlet.livegen.models import CodeGenRequest, CodeGenResult
from gauntlet.project.launch import discover_launch
from gauntlet.run import PRESETS
from gauntlet.synapse import SynapsePlanner


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------- pure builders (NO docker)
def test_gen_candidate_dockerfile_python_from_base_copies_repo(tmp_path):
    launch = discover_launch({"app.py": "print('hi')\n"})  # python brief → no install/build
    df = sandbox._gen_candidate_dockerfile(launch)
    assert df.startswith(f"FROM {sandbox.BASE_TAG}\n")
    assert "COPY --chown=1000:1000 repo/ /work/" in df
    assert "RUN true" in df  # python install/build are no-ops


def test_gen_candidate_dockerfile_node_runs_install_and_build():
    pkg = json.dumps({"scripts": {"build": "tsc", "start": "node dist/server.js"}})
    launch = discover_launch({"package.json": pkg})  # node brief → real install + build
    df = sandbox._gen_candidate_dockerfile(launch)
    assert df.startswith(f"FROM {sandbox.BASE_TAG}\n")
    assert "RUN npm install" in df and "RUN npm run build" in df


def test_gen_probe_argv_is_hardened_internal_net_and_mounts(tmp_path):
    artifacts = tmp_path / "artifacts"
    manifest = tmp_path / "manifest.json"
    probe_path = tmp_path / "gen_probe.py"
    argv = sandbox._gen_probe_argv(
        "cand-image", "cand-name", artifacts, manifest, probe_path,
        slm_alias="slm", slm_port=8000, port=8080,
        serve=["python3", "app.py", "8080"], network="gauntlet-gen-net-x",
    )
    joined = " ".join(argv)
    # hardened flags (ported from the Track P probe run)
    # The container STARTS as root and drops to uid/gid 1000 inside the entrypoint: network_guard.py
    # needs NET_ADMIN to install the fail-closed OUTPUT firewall, and SETUID/SETGID to shed privilege
    # afterwards. Everything else is dropped, and no-new-privileges stops the drop being undone.
    assert argv[argv.index("--user") + 1] == "0:0"
    cap_adds = [argv[i + 1] for i, a in enumerate(argv) if a == "--cap-add"]
    assert cap_adds == ["NET_ADMIN", "SETUID", "SETGID"]
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--security-opt" in argv and "no-new-privileges" in argv
    assert "--pids-limit" in argv and "--tmpfs" in argv and "/tmp" in argv
    # the INTERNAL per-run network, NOT the default bridge / host
    assert argv[argv.index("--network") + 1] == "gauntlet-gen-net-x"
    assert "bridge" not in argv and "host" not in argv
    # gen_probe + manifest mounted READ-ONLY into /probe; artifacts mounted
    assert f"{probe_path}:/probe/gen_probe.py:ro" in argv
    assert f"{manifest}:/probe/manifest.json:ro" in argv
    assert f"{artifacts}:/artifacts" in argv
    # LLM_BASE_URL points at the stub alias; minimal env only (no host secrets)
    assert "LLM_BASE_URL=http://slm:8000/v1" in joined
    assert "LLM_MODEL=stub" in joined
    assert "GAUNTLET_MANIFEST=/probe/manifest.json" in joined
    # the trusted guard is the entrypoint; the probe runs only as its `--` payload, never directly
    assert argv[-8:] == ["cand-image", "python3", "/probe/network_guard.py", "--allow-host", "slm",
                         "--", "python3", "/probe/gen_probe.py"]


def test_gen_probe_argv_carries_no_host_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "AKIAFAKEHOSTSECRET")
    argv = sandbox._gen_probe_argv(
        "img", "name", tmp_path, tmp_path / "m.json", tmp_path / "p.py",
        slm_alias="slm", slm_port=8000, port=8080, serve=["python3", "app.py"], network="net",
    )
    assert "AKIAFAKEHOSTSECRET" not in " ".join(argv)  # the container env is minimal, never os.environ


def test_stub_slm_argv_uses_alias_and_is_hardened(tmp_path):
    stub = tmp_path / "stub_slm.py"
    argv = sandbox._stub_slm_argv("slm-x", "net-x", "slm", 8000, stub)
    assert argv[:3] == ["docker", "run", "-d"]  # detached sidecar
    assert "--network-alias" in argv and argv[argv.index("--network-alias") + 1] == "slm"
    assert argv[argv.index("--network") + 1] == "net-x"
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--security-opt" in argv and "no-new-privileges" in argv
    assert "--memory" in argv and "--pids-limit" in argv
    assert f"{stub}:/probe/stub_slm.py:ro" in argv
    assert argv[-3:] == [sandbox.BASE_TAG, "python3", "/probe/stub_slm.py"]


# --------------------------------------------------------------------------- docker-absent → None
def test_run_generative_sandbox_returns_none_without_docker(monkeypatch):
    monkeypatch.setattr(sandbox, "docker_available", lambda: False)
    out = sandbox.run_generative_sandbox({"checks": []}, {"app.py": "print(1)\n"}, "h")
    assert out is None


# --------------------------------------------------------------------------- path-traversal guard (NO docker)
def test_safe_write_tree_writes_safe_relative_paths(tmp_path):
    base = tmp_path / "repo"
    base.mkdir()
    skipped = sandbox.safe_write_tree(base, {"app.py": "x\n", "server/handlers.py": "y\n"})
    assert skipped == []
    assert (base / "app.py").read_text() == "x\n"
    assert (base / "server" / "handlers.py").read_text() == "y\n"


def test_safe_write_tree_rejects_absolute_and_dotdot_keys(tmp_path):
    base = tmp_path / "repo"
    base.mkdir()
    sentinel = tmp_path / "OUTSIDE"  # a sibling of base the traversal would target
    keys = {
        "/etc/cron.d/evil": "boom\n",                 # absolute → escapes to /etc
        "../../../../etc/passwd": "boom\n",           # parent climb → escapes the context
        "../OUTSIDE": "boom\n",                        # one level up into a sibling
        "ok/nested.py": "fine\n",                     # this one is legitimate
    }
    skipped = sandbox.safe_write_tree(base, keys)
    # all three traversal keys refused; the legit nested file still written
    assert set(skipped) == {"/etc/cron.d/evil", "../../../../etc/passwd", "../OUTSIDE"}
    assert (base / "ok" / "nested.py").read_text() == "fine\n"
    assert not sentinel.exists()  # nothing was written outside the base context
    assert not (tmp_path.parent / "etc").exists()


def test_run_generative_sandbox_rejects_traversal_before_build(monkeypatch):
    # Even with a "docker" present, a traversal key short-circuits to a served=False report and NEVER
    # writes outside the context / builds an image (no docker subprocess is invoked).
    monkeypatch.setattr(sandbox, "docker_available", lambda: True)
    monkeypatch.setattr(sandbox, "_ensure_base", lambda: (True, ""))

    def _no_subprocess(*a, **k):
        raise AssertionError("no docker/subprocess should run when a traversal path is present")

    monkeypatch.setattr(sandbox.subprocess, "run", _no_subprocess)
    report = sandbox.run_generative_sandbox(
        {"checks": []}, {"../../etc/passwd": "boom\n", "app.py": "print(1)\n"}, "h")
    assert report is not None and report.served is False and report.built is False
    assert "unsafe" in report.output


# ------------------------------------------------------ sandbox serve uses manifest start (python port fix)
class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_sandbox_drives_serve_from_manifest_start_so_python_gets_the_port(monkeypatch, tmp_path):
    # The python briefs carry start=["{python}","app.py","{port}"]; the sandbox must pass THAT as
    # GAUNTLET_SERVE (so the app receives the port via argv[1]), not discover_launch's port-less serve.
    monkeypatch.setattr(sandbox, "docker_available", lambda: True)
    monkeypatch.setattr(sandbox, "_ensure_base", lambda: (True, ""))
    captured = {}

    real_probe_argv = sandbox._gen_probe_argv

    def _spy_probe_argv(*a, **k):
        captured["serve"] = k.get("serve", a[8] if len(a) > 8 else None)
        return real_probe_argv(*a, **k)

    monkeypatch.setattr(sandbox, "_gen_probe_argv", _spy_probe_argv)

    def _fake_run(argv, *a, **k):
        if argv[:2] == ["docker", "build"]:
            return _FakeCompleted(0)
        if argv[:3] == ["docker", "network", "create"]:
            return _FakeCompleted(0)
        if argv[:3] == ["docker", "run", "-d"]:  # the stub sidecar
            return _FakeCompleted(0)
        if argv[:2] == ["docker", "run"]:  # the gen-probe → drop a result.json into artifacts
            art = next(argv[i + 1].split(":")[0] for i, x in enumerate(argv)
                       if x == "-v" and argv[i + 1].endswith(":/artifacts"))
            (Path(art) / "result.json").write_text(json.dumps({"served": True, "checks": []}))
            return _FakeCompleted(0)
        return _FakeCompleted(0)  # image rm / network rm / container rm cleanup

    monkeypatch.setattr(sandbox.subprocess, "run", _fake_run)
    manifest = {"start": ["{python}", "app.py", "{port}"], "ready_path": "/", "checks": []}
    report = sandbox.run_generative_sandbox(manifest, {"app.py": "print(1)\n"}, "h",
                                            run_dir=tmp_path)
    assert report is not None and report.served is True
    # the serve handed to the probe is the manifest start (carries the {port} placeholder), not the
    # port-less discover_launch python serve (["python3","app.py"])
    assert captured["serve"] == ["{python}", "app.py", "{port}"]


def test_sandbox_node_brief_serve_falls_back_to_discover_launch(monkeypatch, tmp_path):
    # A node brief declares NO manifest start; the sandbox must use discover_launch's serve (npm run start),
    # which reads PORT from env (gen_probe sets it).
    monkeypatch.setattr(sandbox, "docker_available", lambda: True)
    monkeypatch.setattr(sandbox, "_ensure_base", lambda: (True, ""))
    captured = {}
    real_probe_argv = sandbox._gen_probe_argv

    def _spy_probe_argv(*a, **k):
        captured["serve"] = k.get("serve", a[8] if len(a) > 8 else None)
        return real_probe_argv(*a, **k)

    monkeypatch.setattr(sandbox, "_gen_probe_argv", _spy_probe_argv)

    def _fake_run(argv, *a, **k):
        if argv[:2] == ["docker", "run"] and argv[:3] != ["docker", "run", "-d"]:
            art = next(argv[i + 1].split(":")[0] for i, x in enumerate(argv)
                       if x == "-v" and argv[i + 1].endswith(":/artifacts"))
            (Path(art) / "result.json").write_text(json.dumps({"served": True, "checks": []}))
        return _FakeCompleted(0)

    monkeypatch.setattr(sandbox.subprocess, "run", _fake_run)
    files = {"package.json": json.dumps({"scripts": {"build": "tsc", "start": "node dist/server.js"}}),
             "src/server.ts": "// ts\n"}
    manifest = {"ready_path": "/", "checks": []}  # node: no start declared
    report = sandbox.run_generative_sandbox(manifest, files, "h", run_dir=tmp_path)
    assert report is not None and report.served is True
    assert captured["serve"] == ["npm", "run", "start"]


def test_sandbox_surfaces_sidecar_start_failure_as_infra_not_app(monkeypatch, tmp_path):
    # If the stub-SLM sidecar fails to start, surface the infra cause (not a doomed served=False probe).
    monkeypatch.setattr(sandbox, "docker_available", lambda: True)
    monkeypatch.setattr(sandbox, "_ensure_base", lambda: (True, ""))

    def _fake_run(argv, *a, **k):
        if argv[:3] == ["docker", "run", "-d"]:  # sidecar fails to start
            return _FakeCompleted(1, stderr="no such image")
        if argv[:2] == ["docker", "run"]:
            raise AssertionError("the probe must not run after a sidecar start failure")
        return _FakeCompleted(0)

    monkeypatch.setattr(sandbox.subprocess, "run", _fake_run)
    manifest = {"start": ["{python}", "app.py", "{port}"], "ready_path": "/", "checks": []}
    report = sandbox.run_generative_sandbox(manifest, {"app.py": "print(1)\n"}, "h", run_dir=tmp_path)
    assert report is not None and report.served is False
    assert "sidecar" in report.infrastructure_error


# --------------------------------------------------------------------------- fail-closed without Docker
# Track G used to fall back to building and serving the generated app on the HOST when Docker was
# missing. That fallback is gone (generative/sandbox.py: "There is no host-execution fallback for
# generated code"), and `run_live_brief` now refuses in its first statement — before codegen. These
# tests pin the refusal itself; path-traversal safety is covered at the sandbox boundary by the
# safe_write_tree / run_generative_sandbox tests above, which is where writes actually happen now.
class _NeverRunsCodeGen:
    """Codegen whose use is a test failure: the Docker guard must short-circuit before generation.

    A stub that raises (rather than passing None) keeps the assertion honest — if the guard is ever
    reordered after generation, this fails with a clear message instead of an incidental TypeError."""

    def __init__(self, meta) -> None:
        self.meta = meta

    def generate(self, request: CodeGenRequest) -> CodeGenResult:
        raise AssertionError("run_live_brief generated code with Docker absent")


_NO_DOCKER_PY_BRIEF = {
    "id": "nodocker", "title": "n", "language": "python", "stack": "stdlib", "main_file": "app.py",
    "instruction": "x",
    "manifest": {"start": ["{python}", "app.py", "{port}"], "ready_path": "/",
                 "checks": [{"id": "root", "kind": "rest", "method": "GET", "path": "/",
                             "status": 200, "contains": "x"}]},
}


def test_run_live_brief_refuses_python_brief_without_docker(monkeypatch):
    # `live` does `from .sandbox import docker_available`, binding the function BY VALUE at import,
    # so patching sandbox.docker_available would not be seen here — patch the name on `live`.
    monkeypatch.setattr(live, "docker_available", lambda: False)
    meta = PRESETS["cortex_wrapped"]
    # matches "Docker is unavailable; Track G refuses host execution" (plain substring, no regex chars)
    with pytest.raises(SandboxUnavailable, match="refuses host execution"):
        run_live_brief(_NO_DOCKER_PY_BRIEF, meta, _NeverRunsCodeGen(meta), SynapsePlanner(),
                       HeuristicGenerativeJudge())


def test_run_live_brief_refuses_node_brief_without_docker(monkeypatch):
    # A node/TS brief must never run npm/pnpm on the host either: same refusal, no special case.
    monkeypatch.setattr(live, "docker_available", lambda: False)
    brief = next(b for b in live_briefs() if b["id"] == "chat-web")
    assert brief["requires_sandbox"] is True
    meta = PRESETS["cortex_wrapped"]
    with pytest.raises(SandboxUnavailable, match="refuses host execution"):
        run_live_brief(brief, meta, _NeverRunsCodeGen(meta), SynapsePlanner(),
                       HeuristicGenerativeJudge())


def test_chat_web_brief_is_multifile_ts_with_achievable_manifest():
    brief = next(b for b in live_briefs() if b["id"] == "chat-web")
    assert brief["language"] == "typescript"
    assert brief["requires_sandbox"] is True
    instr = brief["instruction"]
    assert "package.json" in instr and "src/server.ts" in instr and "public/index.html" in instr
    # install/build/serve are recovered from package.json by discover_launch (NOT declared in the manifest)
    assert "build" not in brief["manifest"]
    launch = discover_launch({
        "package.json": json.dumps({"scripts": {"build": "tsc", "start": "node dist/server.js"}}),
        "src/server.ts": "// ts\n",
    })
    assert launch.install and launch.build and launch.serve  # a real install + build + serve plan
    kinds = {c["kind"] for c in brief["manifest"]["checks"]}
    assert {"ui", "rest", "chat"} <= kinds  # a shell, a health endpoint, a chat round-trip


# --------------------------------------------------------------------------- gen_probe check functions
class _AppHandler(BaseHTTPRequestHandler):
    """A tiny stdlib app: a UI shell, a /api/health rest endpoint, and a /api/chat that echoes a reply."""

    def log_message(self, *a) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send(200, b'{"status": "ok"}', "application/json")
        else:
            self._send(200, b'<html><div id="app">hi</div></html>')

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self._send(200, b'{"reply": "pong"}', "application/json")

    def _send(self, code: int, body: bytes, ctype: str = "text/html") -> None:
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server:
    def __init__(self, handler) -> None:
        self._handler = handler

    def __enter__(self) -> str:
        self._port = _free_port()
        self._server = HTTPServer(("127.0.0.1", self._port), self._handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self._port}"

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def test_gen_probe_rest_and_chat_checks_pass_against_app():
    with _Server(_AppHandler) as base:
        rest = gen_probe._rest_check(base, {"id": "health", "method": "GET", "path": "/api/health",
                                            "status": 200, "contains": "ok"})
        chat = gen_probe._chat_check(base, {"id": "send", "path": "/api/chat",
                                            "message": "hi", "min_len": 1, "timeout": 10})
    assert rest["passed"] is True and rest["kind"] == "rest"
    assert chat["passed"] is True and chat["kind"] == "chat"


def test_gen_probe_rest_check_fails_on_missing_content():
    with _Server(_AppHandler) as base:
        rest = gen_probe._rest_check(base, {"id": "h", "method": "GET", "path": "/api/health",
                                            "status": 200, "contains": "NOT_PRESENT"})
    assert rest["passed"] is False


def test_gen_probe_ui_check_tolerated_when_playwright_unavailable():
    # _run_checks degrades a UI check to "unavailable" (passed False) when Playwright can't launch, the
    # same graceful behaviour as the host e2e + Track P probe — it never raises.
    import builtins

    real_import = builtins.__import__

    def _no_playwright(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError("no playwright in this env")
        return real_import(name, *a, **k)

    builtins.__import__ = _no_playwright
    try:
        with _Server(_AppHandler) as base:
            results = gen_probe._run_checks(base, [{"id": "shell", "kind": "ui", "path": "/",
                                                    "selector": "#app", "text": ""}])
    finally:
        builtins.__import__ = real_import
    assert len(results) == 1 and results[0]["id"] == "shell"
    assert results[0]["passed"] is False  # degraded, not crashed


def test_gen_probe_substitute_fills_python_and_port():
    out = gen_probe._substitute(["{python}", "app.py", "{port}"], 8123)
    import sys

    assert out[0] == sys.executable and out[2] == "8123"


# --------------------------------------------------------------------------- stub_slm OpenAI shape
def test_stub_slm_returns_openai_choices_shape():
    with _Server(stub_slm._Handler) as base:
        import urllib.request

        body = json.dumps({"model": "stub", "messages": [{"role": "user", "content": "marco"}]}).encode()
        req = urllib.request.Request(base + "/v1/chat/completions", data=body, method="POST",
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        # /v1/models is OK too
        with urllib.request.urlopen(base + "/v1/models", timeout=5) as resp:
            models = json.loads(resp.read().decode())
    assert isinstance(data.get("choices"), list) and data["choices"]
    assert data["choices"][0]["message"]["content"] == "marco"  # echoes the last user message
    assert models["object"] == "list" and models["data"]


def test_stub_slm_pong_without_user_message():
    with _Server(stub_slm._Handler) as base:
        import urllib.request

        req = urllib.request.Request(base + "/chat/completions", data=b"{}", method="POST",
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    assert data["choices"][0]["message"]["content"] == "pong"
