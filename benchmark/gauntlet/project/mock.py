"""Mock candidate synthesis for Track P (no sandbox/LLM): model the long-horizon build outcome.

Deterministic per (brief, harness). Raw harnesses decay over the very long horizon — they complete
the early capabilities (home/listing/pdp) and drop the tail (payment/order/PWA/tests); Synapse keeps
completeness flat by tracking + validating every requirement. The capability trajectory it yields is
what the real VERTEX scorer consumes, so the mock exercises the genuine scoring path.
"""

from __future__ import annotations

import hashlib

from ..models import HarnessMeta
from ..synapse import SYNAPSE_COVERAGE_BOOST
from .models import Candidate, ProjectBrief


def _jitter(brief_id: str, harness_id: str) -> float:
    digest = hashlib.sha1(f"{brief_id}:{harness_id}".encode()).digest()
    return (digest[0] / 255.0 - 0.5) * 0.08  # ±0.04 deterministic wobble


def _frac(key: str) -> float:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def _completion(brief: ProjectBrief, harness: HarnessMeta, seed: int = 0) -> float:
    base = harness.code_quality
    if harness.uses_synapse:  # plan + validation loop drives the long horizon to completion
        cf = base + (1 - base) * SYNAPSE_COVERAGE_BOOST
    else:  # raw harness decays over a very long, multi-file build
        cf = base * 0.78
    wobble = _jitter(brief.id, harness.id)
    if seed:  # per-seed variance for reliability (pass^k) studies; seed 0 reproduces the canonical run
        wobble += (_frac(f"{brief.id}:{harness.id}:seed{seed}") - 0.5) * 0.12
    return max(0.0, min(1.0, cf + wobble))


def _module_tree(cf: float) -> tuple[dict[str, str], list[str]]:
    """A representative captured repo + module descriptors, richer as completeness rises."""

    files = {
        "server/api.ts": "export const listProducts = () => []\n",
        "ui/components/ProductCard.tsx": "export function ProductCard() { return null }\n",
        "domain/cart.ts": "export class Cart {}\n",
    }
    descriptors = ["http api for catalog/cart", "react component ui layer", "cart domain model"]
    if cf > 0.55:
        files["server/checkout.ts"] = "export const createOrder = () => ({})\n"
        files["tests/cart.test.ts"] = "import {Cart} from '../domain/cart'\n"
        descriptors += ["checkout/order service", "automated tests"]
    if cf > 0.8:
        files["ui/sw.js"] = "self.addEventListener('install', () => {})\n"
        descriptors += ["pwa service worker / offline shell"]
    return files, descriptors


def mock_candidate(brief: ProjectBrief, harness: HarnessMeta, seed: int = 0) -> Candidate:
    cf = _completion(brief, harness, seed)
    descriptors = brief.capability_descriptors
    n_done = round(cf * len(descriptors))
    journeys = [j["id"] for j in brief.acceptance.get("journeys", [])]
    n_journeys = round(cf * len(journeys))
    pwa = [p["id"] for p in brief.acceptance.get("pwa", [])]
    a11y = [a["id"] for a in brief.acceptance.get("a11y", [])]
    rob = [r["id"] for r in brief.acceptance.get("robustness", [])]
    files, modules = _module_tree(cf)
    # seed 0 is the canonical early-first prefix; seeds > 0 realize each journey as an independent
    # Bernoulli(cf) so a full-pass run varies across seeds — the variance the pass^k curve measures.
    journey_pass = (
        {j: (i < n_journeys) for i, j in enumerate(journeys)} if seed == 0
        else {j: _frac(f"{brief.id}:{harness.id}:{j}:s{seed}") < cf for j in journeys}
    )
    return Candidate(
        harness_id=harness.id,
        built=cf > 0.25,
        served=cf > 0.30,
        capabilities=list(descriptors[:n_done]),  # early-first; raw drops the tail
        journey_pass=journey_pass,
        pwa_a11y={k: (i / max(1, len(pwa) + len(a11y))) < cf for i, k in enumerate(pwa + a11y)},
        robustness={k: (i / max(1, len(rob))) < cf for i, k in enumerate(rob)},
        files=files,
        module_descriptors=modules,
        screenshots={},  # mock has no real renders; the vision judge falls back to a proxy
    )
