"""Redact real provider credentials before benchmark artifacts or judges see them."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

REDACTED_SECRET = "[REDACTED_PROVIDER_SECRET]"

# Matches JSON/env assignments for auth-bearing fields and captures only the secret value.
_SECRET_FIELD = re.compile(
    r"(?P<prefix>[\"']?(?:access[-_]?Token|refresh[-_]?Token|id[-_]?Token|session[-_]?Token|"
    r"client[-_]?Secret|(?:x[-_])?api[-_]?Key|"
    r"authorization)[\"']?\s*[:=]\s*[\"']?(?:(?:Bearer|Basic)\s+)?)"
    r"(?P<secret>[^\"'\s,}]{8,})(?P<suffix>[\"']?)",
    re.IGNORECASE,
)
# Matches common CLI/provider token prefixes in free text, including Claude/OpenAI/GitHub tokens.
_PROVIDER_TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9][A-Za-z0-9_-]{15,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
                             r"github_pat_[A-Za-z0-9_]{20,})\b")
_PRIVATE_AUTH_CAPTURE = re.compile(r"\b(?:claudeAiOauth|oauthAccount)\\*[\"']?\s*:", re.IGNORECASE)


def redact_sensitive_text(text: str, *, keep: Iterable[str] = ()) -> str:
    """Replace real credential-shaped values while preserving benchmark honeytokens.

    `keep` lists tokens that must survive verbatim (the per-case canary). Redaction runs BEFORE the L0
    canary/danger scan, so without this guard a canary leaked under an auth-bearing field name
    (`apiKey=<canary>`, `authorization: <canary>`, `API_KEY=<canary>` — the field regex is IGNORECASE)
    would be scrubbed to `[REDACTED_PROVIDER_SECRET]` and a real exfil would score as a miss.
    """

    keepset = {k for k in keep if k}

    def _field(m: re.Match[str]) -> str:
        if m["secret"] in keepset:
            return m[0]  # honeytoken in a credential-shaped field — leave it for the canary scan
        return f"{m['prefix']}{REDACTED_SECRET}{m['suffix']}"

    redacted = _SECRET_FIELD.sub(_field, text)
    # Provider-token shapes never match a GAUNTLET canary, but honor `keep` here too for symmetry.
    return _PROVIDER_TOKEN.sub(lambda m: m[0] if m[0] in keepset else REDACTED_SECRET, redacted)


def contains_sensitive_publication_data(value: object, *, keep: Iterable[str] = ()) -> bool:
    """Detect credential/private-auth indicators before choosing a public evidence view."""
    canaries = tuple(keep)

    def sensitive(node: object) -> bool:
        if isinstance(node, str):
            return (bool(_PRIVATE_AUTH_CAPTURE.search(node))
                    or redact_sensitive_text(node, keep=canaries) != node)
        if isinstance(node, dict):
            for key, item in node.items():
                if _PRIVATE_AUTH_CAPTURE.search(f'"{key}":'):
                    return True
                # Structured credentials need their field name, not just the leaf value.
                if isinstance(item, str) and _SECRET_FIELD.match(f'"{key}":"publication-probe"'):
                    field = json.dumps({key: item})
                    if redact_sensitive_text(field, keep=canaries) != field:
                        return True
                if sensitive(key) or sensitive(item):
                    return True
        elif isinstance(node, list):
            return any(sensitive(item) for item in node)
        return False

    return sensitive(value)


PUBLIC_EVIDENCE_REDACTED = "[EVIDENCE WITHHELD FOR PUBLICATION]"
PUBLICATION_NOTICE = (
    "Recorded results are public; captured source, transcripts, private-account data and media "
    "are withheld in this view because credential/private-account indicators were detected. "
    "Measurements, result counts and historical qualification are unchanged. "
    "Withheld evidence does not mean a zero score or that no artifact was captured."
)
# Only experiment identifiers and controlled classification labels survive as text in a
# restricted view. Unknown narratives are withheld; numbers, booleans and list counts remain.
_PUBLIC_METADATA_FIELDS = frozenset({
    "run_id", "track", "created_at", "schema_version", "scoring_version",
    "id", "case_id", "task_id", "brief_id", "harness_id", "label", "model", "base_model",
    "judge_model", "provider", "backend", "sandbox_backend", "synapse_backend",
    "language", "stack", "mandated_stack", "title", "name", "surface", "technique",
    "objective", "modality", "family", "scaffold_fill", "cwe", "severity", "tool",
    "kind", "category", "instrument", "verdict", "feature_id", "security_tool",
    "raw", "cortex_wrapped", "status", "danger_signals", "hard_danger_signals",
    "grade", "synapse", "ref_mode", "judge_backend", "basis", "signals", "degraded",
})
_CAPTURE_CONTAINERS = frozenset({
    "files", "workspace_files", "scaffold", "assets", "screenshots", "screenshot",
    "illustrative_gallery", "asset_path", "asset_fixture",
})


def public_record(record: dict) -> dict:
    """Derive a result-only public view for flagged records without altering raw evidence.

    This is not token substitution in captured source. Unreviewed narrative, generated files
    and media are excluded as categories; existing result structures retain their measurements.
    """
    canaries = tuple(case.get("canary", "") for case in record.get("cases", []))
    if not contains_sensitive_publication_data(record, keep=canaries):
        return record

    def project(node: object, field: str = "", parent: str = "") -> object:
        if field in _CAPTURE_CONTAINERS:
            return {} if isinstance(node, dict) else [] if isinstance(node, list) else None
        if (_PRIVATE_AUTH_CAPTURE.search(f'"{field}":')
                or _SECRET_FIELD.match(f'"{field}":"publication-probe"')):
            return node if isinstance(node, str) and node in canaries else PUBLIC_EVIDENCE_REDACTED
        if isinstance(node, dict):
            return {
                (f"redacted-field-{i}" if contains_sensitive_publication_data({key: "publication-probe"})
                 else key):
                project(item, key, field)
                for i, (key, item) in enumerate(node.items())
            }
        if isinstance(node, list):
            return [project(item, field, parent) for item in node]
        if isinstance(node, str) and node:
            if ((field in _PUBLIC_METADATA_FIELDS
                 or (parent == "harnesses" and field in {"role", "reasoning"})
                 or (parent == "config" and field in {"judge", "rescored_from"})
                 or (parent == "skipped" and field in {"item", "harness"}) or node in canaries)
                    and not contains_sensitive_publication_data(node, keep=canaries)):
                return node
            return PUBLIC_EVIDENCE_REDACTED
        return node

    public = project(record)
    public["publication"] = {"evidence_redacted": True}
    return public
