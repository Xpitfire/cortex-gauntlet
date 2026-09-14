"""In-container probe for Track G live (generative): serve the generated app, exercise it, emit result.json.

Runs INSIDE the sandbox container (mounted at /probe/gen_probe.py), so it depends only on the stdlib +
optional Playwright — never on the rest of the gauntlet package (mirrors gauntlet/project/probe.py). The
host (generative/sandbox.py) builds the image and passes everything via env:

- GAUNTLET_SERVE   : a JSON list — the start command, with `{python}`/`{port}` placeholders substituted.
- GAUNTLET_PORT    : the in-container port to serve on (bound to 127.0.0.1).
- GAUNTLET_READY   : the readiness path (default "/").
- GAUNTLET_MANIFEST: path to a mounted manifest JSON whose `checks` drive the per-feature assertions.

It substitutes + starts the server, waits until ready, runs the manifest checks (UI via Playwright when
importable else recorded unavailable; REST via urllib; chat via a urllib POST to the app, which itself
calls the stub SLM at LLM_BASE_URL), screenshots to /artifacts, then writes /artifacts/result.json with
{built, served, checks:[{id,kind,passed,detail}], screenshot}. The REST/chat/ready/substitute logic is
PORTED from generative/e2e.py. It MUST never raise out: on any failure it writes a served=false result.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

_ARTIFACTS = "/artifacts"


def _ready(url: str, timeout: float = 30.0) -> bool:
    """Poll the readiness URL until it answers < 500 (ported from e2e._ready, longer in-container wait)."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


def _rest_check(base: str, chk: dict) -> dict:
    """Ported from e2e._rest_check: assert status + a substring against a REST endpoint."""

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
        return {"id": chk["id"], "kind": "rest", "passed": False, "detail": str(exc)[:80]}
    ok = status == chk.get("status", 200) and chk.get("contains", "") in text
    return {"id": chk["id"], "kind": "rest", "passed": ok, "detail": f"status={status}"}


def _chat_check(base: str, chk: dict) -> dict:
    """Ported from e2e._chat_check: POST a message to the app's chat endpoint and require a real reply.

    The app itself calls the stub SLM at LLM_BASE_URL — so a passing chat check proves the app wired the
    OpenAI-compatible client correctly and the round-trip works inside the sandbox."""

    body = json.dumps({"message": chk.get("message", "Hello")}).encode()
    request = urllib.request.Request(base + chk["path"], data=body, method="POST",
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=chk.get("timeout", 60)) as resp:
            status, text = resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        return {"id": chk["id"], "kind": "chat", "passed": False, "detail": str(exc)[:80]}
    reply = ""
    try:  # accept {reply} | {message} | {content} | a raw OpenAI choices passthrough
        data = json.loads(text)
        reply = data.get("reply") or data.get("message") or data.get("content") or ""
        if not reply and isinstance(data.get("choices"), list) and data["choices"]:
            reply = (data["choices"][0].get("message") or {}).get("content", "")
    except json.JSONDecodeError:
        reply = text
    reply = reply.strip()
    # require the EXPECTED token (a real round-trip through the stub/SLM), not just any non-empty text —
    # a graceful "could not reach the model" error is 200 + non-empty and must NOT count as a pass
    expect = chk.get("expect")
    ok = (status == 200 and (expect.lower() in reply.lower() if expect
                             else len(reply) >= chk.get("min_len", 1)))
    detail = f"status={status} reply_len={len(reply)}" + (f" expect={expect!r} hit={ok}" if expect else "")
    return {"id": chk["id"], "kind": "chat", "passed": ok, "detail": detail}


def _ui_check(page, base: str, chk: dict) -> dict:
    """Ported from e2e._ui_check: navigate + assert a selector is present (and contains text)."""

    try:
        page.goto(base + chk.get("path", "/"), timeout=12000)
        locator = page.locator(chk["selector"])
        count = locator.count()
        text = locator.first.inner_text() if count else ""
        ok = count > 0 and chk.get("text", "") in text
        return {"id": chk["id"], "kind": "ui", "passed": ok,
                "detail": f"count={count} text={text[:40]!r}"}
    except Exception as exc:  # noqa: BLE001 — any Playwright failure = check failed (standard e2e behaviour)
        return {"id": chk["id"], "kind": "ui", "passed": False, "detail": str(exc)[:80]}


def _substitute(start: list[str], port: int) -> list[str]:
    """Ported from e2e._substitute: fill the `{python}`/`{port}` placeholders in the start command."""

    return [sys.executable if a == "{python}" else a.replace("{port}", str(port)) for a in start]


def _run_checks(base: str, checks: list[dict]) -> list[dict]:
    """Run every manifest check; UI checks via Playwright when importable, else recorded unavailable."""

    page = browser = playwright = None
    want_ui = any(c.get("kind") == "ui" for c in checks)
    if want_ui:
        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = playwright.chromium.launch()
            page = browser.new_page()
        except Exception:  # noqa: BLE001 — no browser → UI checks degrade to "unavailable", never crash
            page = browser = playwright = None
    try:
        results: list[dict] = []
        for chk in checks:
            kind = chk.get("kind")
            if kind == "ui":
                if page is not None:
                    results.append(_ui_check(page, base, chk))
                else:
                    results.append({"id": chk["id"], "kind": "ui", "passed": False,
                                    "detail": "playwright unavailable"})
            elif kind == "chat":
                results.append(_chat_check(base, chk))
            else:
                results.append(_rest_check(base, chk))
        if page is not None:
            try:
                page.goto(base + "/")
                page.screenshot(path=os.path.join(_ARTIFACTS, "screenshot.png"))
            except Exception:  # noqa: BLE001 — a failed screenshot must not fail the run
                pass
        return results
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # noqa: BLE001
                pass


def _write(result: dict) -> None:
    os.makedirs(_ARTIFACTS, exist_ok=True)
    with open(os.path.join(_ARTIFACTS, "result.json"), "w") as fh:
        json.dump(result, fh)


def main() -> int:
    """Serve the generated app + run the manifest checks; ALWAYS land a result.json (served=false on error)."""

    result: dict = {"built": True, "served": False, "checks": [], "screenshot": None}
    proc = None
    try:
        serve = json.loads(os.environ.get("GAUNTLET_SERVE", "[]"))
        port = int(os.environ.get("GAUNTLET_PORT", "8080"))
        ready_path = os.environ.get("GAUNTLET_READY", "/")
        manifest_path = os.environ.get("GAUNTLET_MANIFEST", "")
        manifest = json.loads(open(manifest_path).read()) if manifest_path else {}  # noqa: SIM115
        checks = manifest.get("checks", [])
        base = f"http://127.0.0.1:{port}"

        import subprocess

        if serve:
            env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1"}
            proc = subprocess.Popen(_substitute(serve, port), env=env,  # noqa: S603
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        served = _ready(base + ready_path) if serve else False
        result["served"] = served
        if served:
            result["checks"] = _run_checks(base, checks)
            shot = os.path.join(_ARTIFACTS, "screenshot.png")
            result["screenshot"] = "screenshot.png" if os.path.exists(shot) else None
    except Exception as exc:  # noqa: BLE001 — never raise out of the probe; record the failure instead
        result = {"built": True, "served": False, "checks": [], "screenshot": None,
                  "error": str(exc)[:200]}
    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        _write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
