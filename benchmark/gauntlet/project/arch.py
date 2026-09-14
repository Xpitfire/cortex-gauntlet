"""Derive natural-language architecture descriptors from a repo file tree — the candidate side of
VERTEX-architecture.

Bare top-level directory names ("src", "public") barely match the architecture *anchors* (full
sentences like "clear separation between backend API and frontend UI"), so the cross-similarity is
near chance. These role-level descriptors are grounded in real path + light content evidence (a
descriptor is emitted only when the repo actually shows that concern), which gives VERTEX real signal
while staying honest and discriminative — a repo missing a layer simply does not earn its descriptor.
"""

from __future__ import annotations

import re

# domain nouns surfaced by file/dir names — the repo's OWN vocabulary, not a fixed schema
_ENTITY = re.compile(
    r"\b(cart|order|product|variant|user|account|payment|checkout|catalog|"
    r"inventory|session|wishlist|category|review|address|shipping)\b")
_ENV = re.compile(r"process\.env|os\.environ|import\.meta\.env|getenv|dotenv")


def architecture_descriptors(files: dict[str, str]) -> list[str]:
    """Role-level descriptors of the architecture evidenced by the repo (paths + light content)."""

    if not files:
        return []
    paths = list(files)
    low = " ".join(paths).lower()
    blob = "\n".join(c for c in files.values() if isinstance(c, str))[:200_000]  # bounded content scan
    desc: list[str] = []
    if any(k in low for k in ("server", "/api", "route", "controller", "backend", "handler", "endpoint")):
        desc.append("backend API server with HTTP routing and endpoints")
    if any(k in low for k in ("public/", "component", "/ui", "pages", "views", "frontend", "client",
                              ".html", ".css", ".tsx", ".jsx")):
        desc.append("frontend UI layer with pages, views and components")
    if any(k in low for k in ("model", "domain", "service", "store", "entity", "schema", "repository")):
        desc.append("domain and service layer distinct from transport and routing")
    entities = sorted(set(_ENTITY.findall(low)))
    if entities:
        desc.append("data models for " + ", ".join(entities))
    if any("test" in p.lower() or ".spec." in p or ".test." in p for p in paths):
        desc.append("automated tests colocated or in a dedicated test tree")
    if any(k in low for k in (".env", "config", "settings")) or _ENV.search(blob):
        desc.append("configuration and secrets read from the environment")
    return desc
