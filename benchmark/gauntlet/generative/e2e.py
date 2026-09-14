"""Real build + serve + e2e for a generated web app.

Pipeline: build gate (optional build command) -> start the server -> wait until ready ->
run per-feature checks (Playwright UI assertions + black-box REST + state) -> screenshot ->
teardown. This is the measured functional signal for Track G live, replacing the modeled one.

Untrusted generated apps should run in a Docker sandbox (Phase 4); this runner uses a temp
workspace + a bound-to-127.0.0.1 server, which is acceptable for the trusted fixture.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class CheckResult:
    id: str
    kind: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class E2EReport:
    built: bool
    served: bool
    checks: list[CheckResult] = field(default_factory=list)
    screenshot: str | None = None
    output: str = ""
    infrastructure_error: str = ""

    @property
    def passed(self) -> int:
        return sum(c.passed for c in self.checks)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _ready(url: str, timeout: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


def _build(workspace: Path, build_cmd: list[str] | None) -> tuple[bool, str]:
    if not build_cmd:
        return True, ""
    try:
        proc = subprocess.run(build_cmd, cwd=workspace, capture_output=True, text=True,
                              timeout=600, check=False)
    except (subprocess.SubprocessError, OSError) as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-1200:]


def _rest_check(base: str, chk: dict) -> CheckResult:
    body = chk.get("body", "").encode() if chk.get("method") == "POST" else None
    request = urllib.request.Request(
        base + chk["path"], data=body, method=chk.get("method", "GET"),
        headers={"content-type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as resp:
            status, text = resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        return CheckResult(chk["id"], "rest", False, str(exc)[:80])
    ok = status == chk.get("status", 200) and chk.get("contains", "") in text
    return CheckResult(chk["id"], "rest", ok, f"status={status}")


def _chat_check(base: str, chk: dict) -> CheckResult:
    """POST a user message to the app's chat endpoint and verify the assistant reply reflects a REAL
    round-trip through the SLM — not a graceful "could not reach the model" error. The probe asks the
    model to "Reply with the single word: pong"; the stub echoes the prompt and a real SLM obeys it, so
    both contain `expect` ("pong"), while an unreachable-model error does not. Without this, a 200 + any
    non-empty text (including the error message) counted as a pass — the 7/7 false positive."""

    body = json.dumps({"message": chk.get("message", "Hello")}).encode()
    request = urllib.request.Request(base + chk["path"], data=body, method="POST",
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=chk.get("timeout", 60)) as resp:
            status, text = resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        return CheckResult(chk["id"], "chat", False, str(exc)[:80])
    reply = ""
    try:  # accept {reply} | {message} | {content} | a raw OpenAI choices passthrough
        data = json.loads(text)
        reply = data.get("reply") or data.get("message") or data.get("content") or ""
        if not reply and isinstance(data.get("choices"), list) and data["choices"]:
            reply = (data["choices"][0].get("message") or {}).get("content", "")
    except json.JSONDecodeError:
        reply = text
    reply = reply.strip()
    expect = chk.get("expect")
    ok = (status == 200 and (reply.lower().find(expect.lower()) >= 0 if expect
                             else len(reply) >= chk.get("min_len", 1)))
    detail = f"status={status} reply_len={len(reply)}" + (f" expect={expect!r} hit={ok}" if expect else "")
    return CheckResult(chk["id"], "chat", ok, detail)


def _ui_check(page, base: str, chk: dict) -> CheckResult:
    if page is None:  # browser unavailable: the check cannot run, so it scores 0 with a clear reason
        return CheckResult(chk["id"], "ui", False, "no browser: playwright or chromium unavailable")
    try:
        page.goto(base + chk.get("path", "/"), timeout=12000)
        locator = page.locator(chk["selector"])
        count = locator.count()
        text = locator.first.inner_text() if count else ""
        ok = count > 0 and chk.get("text", "") in text
        return CheckResult(chk["id"], "ui", ok, f"count={count} text={text[:40]!r}")
    except Exception as exc:  # any Playwright failure = check failed (standard e2e behaviour)
        return CheckResult(chk["id"], "ui", False, str(exc)[:80])


def _substitute(start: list[str], port: int) -> list[str]:
    return [sys.executable if a == "{python}" else a.replace("{port}", str(port)) for a in start]


def run_e2e(workspace: Path, manifest: dict, screenshot: Path | None = None,
            env: dict | None = None) -> E2EReport:
    built, build_out = _build(workspace, manifest.get("build"))
    if not built:
        return E2EReport(built=False, served=False, output=build_out)

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    # `env` (when given) is the FULL environment for the served app — the caller merges os.environ +
    # LLM_BASE_URL/LLM_MODEL so an SLM-backed app can reach the local model. None → inherit the parent.
    proc = subprocess.Popen(
        _substitute(manifest["start"], port), cwd=workspace, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        if not _ready(base + manifest.get("ready_path", "/")):
            out = (proc.stdout.read().decode(errors="replace") if proc.stdout else "")[-600:]
            return E2EReport(built=True, served=False, output="server not ready\n" + out)

        page = browser = playwright = None
        shot_rel = None
        if any(c["kind"] == "ui" for c in manifest["checks"]):
            # A missing playwright package OR an installed package whose browser binary was never
            # downloaded (`playwright install`) must not sink the whole run: the REST and chat checks
            # are still meaningful signal. Degrade to page=None — the ui checks then fail individually
            # with a stated reason — instead of raising out of run_e2e as an evaluator crash.
            try:
                from playwright.sync_api import Error as PlaywrightError
                from playwright.sync_api import sync_playwright
            except ImportError:
                pass  # package absent
            else:
                try:
                    playwright = sync_playwright().start()
                    browser = playwright.chromium.launch()
                    page = browser.new_page()
                except PlaywrightError:  # e.g. "Executable doesn't exist" before `playwright install`
                    if playwright is not None:
                        playwright.stop()
                    page = browser = playwright = None
        try:
            checks = [
                _ui_check(page, base, c) if c["kind"] == "ui"
                else _chat_check(base, c) if c["kind"] == "chat"
                else _rest_check(base, c)
                for c in manifest["checks"]
            ]
            if page and screenshot:
                page.goto(base + "/")
                page.screenshot(path=str(screenshot))
                shot_rel = f"assets/{screenshot.name}"
        finally:
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
        return E2EReport(built=True, served=True, checks=checks, screenshot=shot_rel, output=build_out)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
