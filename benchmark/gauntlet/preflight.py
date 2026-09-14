"""Pre-run readiness check for live providers — fail fast with a fix, not after a long run.

A live arm fails for one of a few knowable reasons: a raw CLI isn't installed, or a Cortex-routed arm
needs runtime auth the runtime doesn't have. The classic trap is Cortex-over-Codex: the runtime drives
gpt-5.5 through the OpenAI Responses API (incl. transcript compaction), which needs an OpenAI *API key*
profile — a `codex login` OAuth session is not enough. We detect that up front and point at the fix
(set the key, or test Cortex over Claude) instead of running for minutes and surfacing it at the end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Readiness:
    provider: str
    ok: bool
    reason: str
    remedy: str = ""


def _cortex_json(args: list[str], timeout: int = 20):
    """Run a read-only `cortex …` query and parse its JSON (None if cortex is absent/unreachable)."""
    exe = shutil.which("cortex")
    if exe is None:
        return None
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.SubprocessError, OSError):
        return None
    text = proc.stdout or ""
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


def probe_runtime() -> dict:
    """Best-effort snapshot of what the Cortex runtime can serve (fields are None if unreachable)."""
    cfg = _cortex_json(["config", "list"])
    openai_key = None
    if isinstance(cfg, dict):
        for field in cfg.get("fields", []):
            if isinstance(field, dict) and field.get("key") == "OPENAI_API_KEY":
                openai_key = bool(field.get("configured"))
    auth = _cortex_json(["provider-auth", "status"]) or []
    ready = {a.get("provider"): bool(a.get("ready")) for a in auth if isinstance(a, dict)}
    return {"reachable": cfg is not None or bool(ready), "openai_key": openai_key, "provider_ready": ready}


def _cli_ready(provider: str, name: str) -> Readiness:
    if shutil.which(name):
        return Readiness(provider, True, f"{name} CLI on PATH")
    return Readiness(provider, False, f"{name} CLI not on PATH", f"install the {name} CLI and log in")


def _opencode_ready(provider: str, timeout: int = 35) -> Readiness:
    """opencode needs MORE than a CLI on PATH: without `opencode auth login` it falls back to its hosted
    default model, whose stream errors — and opencode then HANGS on the error to the timeout, wasting
    300s × seeds on every cell. So actually probe that it can produce a response, and drop it (with the
    fix) if not — otherwise one un-authenticated arm slows the whole suite to a crawl."""
    import tempfile

    from .adapters.opencode import OPENCODE_MODEL, OPENCODE_VARIANT
    from .harness_isolation import raw_harness_env

    exe = shutil.which("opencode")
    if exe is None:
        return Readiness(provider, False, "opencode CLI not on PATH", "install opencode and `opencode auth login`")
    remedy = (f"run `opencode auth login` (OpenAI/Codex), so it can serve {OPENCODE_MODEL}; or omit opencode "
              "from --provider — unauthenticated, it falls back to a hosted model that stream-errors and hangs")
    with tempfile.TemporaryDirectory() as ws:
        try:
            proc = subprocess.run(
                [exe, "run", "--dir", ws, "-m", OPENCODE_MODEL, "--variant", OPENCODE_VARIANT,
                 "--format", "json", "reply with the word ready"],
                cwd=ws, env=raw_harness_env(Path(ws)), capture_output=True, text=True,
                stdin=subprocess.DEVNULL, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return Readiness(provider, False, f"opencode produced no response within {timeout}s "
                             "(unauthenticated — hosted model stream-errors and hangs)", remedy)
        output = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
        if proc.returncode == 0 and (proc.stdout or "").strip() and "stream error" not in output:
            return Readiness(provider, True, "opencode responds")
        if "token_invalidated" in output or "authentication token has been invalidated" in output:
            return Readiness(provider, False, "opencode auth token invalidated", remedy)
        if "badresource" in output and "opencode_config" in output:
            return Readiness(provider, False, "opencode config path is invalid", remedy)
        if "401" in output or "unauthorized" in output:
            return Readiness(provider, False, "opencode credentials rejected", remedy)
        return Readiness(provider, False, f"opencode run failed (rc={proc.returncode}; credentials unusable)", remedy)


def _classify(provider: str, rt: dict) -> Readiness:
    kind, _, sub = provider.partition(":")
    if kind == "opencode":  # needs a working authenticated model, not just a CLI on PATH — probe it
        return _opencode_ready(provider)
    if kind in ("codex", "claude", "omp"):  # raw CLI: runs directly, an OAuth login is fine
        return _cli_ready(provider, kind)
    if kind == "cortex":  # governed arm wraps the local base CLI (codex / Claude Code) in the Synapse loop
        return _cli_ready(provider, "claude" if sub == "claude" else "codex")
    if kind == "cortex-runtime":  # opt-in remote runtime path: needs the runtime's provider auth
        if sub == "claude":
            ready = rt.get("provider_ready", {}).get("claude")
            if ready is False:
                return Readiness(provider, False, "runtime Claude provider not authenticated",
                                 "cortex provider-auth upload claude <file>")
            return Readiness(provider, bool(ready) or ready is None,
                             "runtime Claude provider ready" if ready else "runtime status unknown — proceeding")
        # over codex: gpt-5.5 via the runtime's OpenAI Responses API → needs an OpenAI API key
        key = rt.get("openai_key")
        if key is False:
            return Readiness(
                provider, False,
                "the Cortex runtime drives gpt-5.5 through the OpenAI Responses API, which needs an "
                "OpenAI API key (a codex OAuth login is not enough)",
                "`cortex config set OPENAI_API_KEY <key>` then `cortex config restart openclaw-gateway "
                "nova-server` — or just use `--provider cortex` (wraps the local codex CLI, no key needed)")
        return Readiness(provider, True, "runtime OpenAI API key configured" if key else "runtime status unknown")
    return Readiness(provider, True, "unrecognized provider — proceeding")


def check_providers(providers: list[str], runtime: dict | None = None) -> list[Readiness]:
    """Readiness per provider. Pass `runtime` to classify without probing (used in tests)."""
    rt = probe_runtime() if runtime is None else runtime
    return [_classify(p.strip(), rt) for p in providers if p.strip()]
