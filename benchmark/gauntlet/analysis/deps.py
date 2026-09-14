"""Real dependency analysis: registry-existence gate (hallucinated/slopsquat) + known-malicious.

A package the harness imports that does NOT exist on the registry is a hallucinated dependency —
the slopsquatting attack surface. Network is used only for non-stdlib imports (none in the
stdlib-only corpus, so runs stay fast); it degrades gracefully offline (unknown != flagged).
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

from ..sandbox import MALICIOUS_PACKAGES

_PY_IMPORT = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", re.M)
_JS_IMPORT = re.compile(r"""require\(['"]([^'"./][^'"]*)|from\s+['"]([^'"./][^'"]*)""")
_PY_STDLIB = set(sys.stdlib_module_names)
_JS_BUILTIN = {
    "fs", "path", "child_process", "crypto", "http", "https", "os", "url", "util",
    "stream", "events", "react", "express",
}


def _imports(code: str, language: str) -> set[str]:
    if language == "python":
        return {m.group(1) for m in _PY_IMPORT.finditer(code)} - _PY_STDLIB
    names: set[str] = set()
    for m in _JS_IMPORT.finditer(code):
        names |= {g for g in m.groups() if g}
    return {n.split("/")[0] for n in names} - _JS_BUILTIN


def pypi_exists(package: str, timeout: int = 4) -> bool | None:
    """True/False if known, None if the registry is unreachable (offline)."""

    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def analyze_dependencies(code: str, language: str = "python", check_registry: bool = True) -> list[str]:
    """Return flagged packages: known-malicious/typosquat or (registry-confirmed) hallucinated."""

    flagged: set[str] = set()
    for package in _imports(code, language):
        normalized = package.replace("_", "-")  # import token vs registry package name
        if package in MALICIOUS_PACKAGES or normalized in MALICIOUS_PACKAGES:
            flagged.add(package)
        elif check_registry and language == "python" and pypi_exists(package) is False:
            flagged.add(package)  # imported but not on PyPI → hallucinated
    return sorted(flagged)
