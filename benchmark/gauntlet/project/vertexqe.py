"""VERTEX-QE — reference-free / estimated references for VERTEX (see the docs paper, section 5.1.1).

Replaces VERTEX's hand-authored hidden reference (acceptance.json `capability_descriptors` /
`architecture_anchors`) with references ESTIMATED from public sources, so the metric scales to
un-authored briefs while keeping VERTEX's kernel + guarantees. Each part of the reference is routed to
the source that carries its information (the §6.1 principle):

  - capability  ← the public **brief** (it lists what the app must do)            [source-as-reference]
  - architecture ← a curated **reference-repo corpus** distribution               [typicality / MAUVE]
  - calibration ← the **peer pool** of arms on the same brief (leave-one-out)      [MBR / consensus]

Reference modes: `authored` | `brief` | `repo` | `qe` (weak-supervision aggregate of brief+repo,
per-candidate) | `consensus` (qe + leave-one-out peer consensus + contrastive calibration, computed
pool-level in `score_pool`). CLI runs pass the resolved mode explicitly; the legacy
`GAUNTLET_VERTEX_REF` env var remains a low-level fallback.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from ..analysis.embedding import cosine, embed_texts
from ..analysis.vertex import resolve_model
from .arch import architecture_descriptors
from .models import Candidate, ProjectBrief

_CORPUS = (Path(__file__).resolve().parents[2]
           / "suites" / "generative" / "fixtures" / "storefront" / "arch_corpus.json")
_DEDUP_SIM = 0.92  # two descriptors above this cosine are the "same" node — dedup the union
VALID_REF_MODES = ("authored", "brief", "repo", "qe", "consensus")
VERTEX_REF_CHOICES = ("auto", *VALID_REF_MODES)


def resolve_ref_mode(mode: str | None = None, *, live: bool = False) -> str:
    """Resolve CLI/user reference selection. `auto` is reference-free for live, authored for mock."""

    raw = (mode if mode is not None else os.environ.get("GAUNTLET_VERTEX_REF", "authored")).strip().lower()
    raw = raw or "auto"
    if raw == "auto":
        return "qe" if live else "authored"
    if raw not in VALID_REF_MODES:
        raise ValueError(f"unknown VERTEX reference mode {raw!r}; choose one of {VERTEX_REF_CHOICES}")
    return raw


def ref_mode() -> str:
    """The active fallback reference mode (`GAUNTLET_VERTEX_REF`, default `authored`)."""

    return resolve_ref_mode()


# ---- Phase 1: brief extraction (capability ← brief; architecture hints ← engineering bullets) --------
def _section(md: str, header_substr: str) -> list[str]:
    """Lines belonging to the first `## …` section whose header contains `header_substr`."""

    out, capturing = [], False
    for ln in md.splitlines():
        if ln.lstrip().startswith("##"):
            capturing = header_substr.lower() in ln.lower()
            continue
        if capturing:
            out.append(ln)
    return out


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold**
    text = re.sub(r"`(.+?)`", r"\1", text)         # `code`
    text = re.sub(r"\([^)]*\)", "", text)          # (parentheticals)
    return re.sub(r"\s+", " ", text).strip(" .;:-")


def extract_brief_descriptors(brief: ProjectBrief) -> tuple[list[str], list[str]]:
    """(capabilities, architecture) parsed from the public brief: the numbered shopper outcomes and the
    'Engineering expectations' bullets under 'What it must do' — no authored acceptance file involved."""

    caps: list[str] = []
    arch: list[str] = []
    in_eng = False
    cur: list[str] | None = None
    for ln in _section(brief.prompt, "what it must do"):
        if "engineering expectation" in ln.lower():
            in_eng, cur = True, None
            continue
        m = re.match(r"\s*(?:\d+\.|[-*])\s+(.*)", ln)
        if m:
            cur = arch if in_eng else caps
            cur.append(_clean(m.group(1)))
        elif ln.strip() and cur and ln[:1].isspace():  # continuation line of the previous item
            cur[-1] = _clean(cur[-1] + " " + ln.strip())
    return [c for c in caps if c], [a for a in arch if a]


# ---- Phase 2: reference-repo corpus (architecture typicality prior) ----------------------------------
@lru_cache(maxsize=1)
def load_arch_corpus() -> list[list[str]]:
    """Per-repo architecture descriptor sets from the curated corpus (descriptors only, never source)."""

    if not _CORPUS.exists():
        return []
    data = json.loads(_CORPUS.read_text())
    return [r["descriptors"] for r in data.get("repos", []) if r.get("descriptors")]


def repo_arch_reference() -> list[str]:
    """The corpus as one deduped reference pool — a candidate is scored on typicality vs this region."""

    return _dedup([d for repo in load_arch_corpus() for d in repo])


# ---- Phase 3: peer-pool consensus (leave-one-out agreement across arms) -------------------------------
def consensus_descriptors(pools: list[list[str]], exclude: int, *, k: int = 2,
                          sim: float = 0.78) -> list[str]:
    """Descriptors that recur (cosine ≥ `sim`) in ≥`k` of the OTHER arms' pools — the agreement signal a
    competent-but-latent reference would carry (MBR / wisdom-of-crowds). Leave-one-out so a candidate
    never references itself."""

    others = [p for j, p in enumerate(pools) if j != exclude and p]
    if len(others) < k:
        return []
    flat = _dedup([d for p in others for d in p])
    if not flat:
        return []
    texts = flat + [d for p in others for d in p]
    vecs, _ = embed_texts(texts, resolve_model())
    cand_vecs = vecs[: len(flat)]
    # for each unique descriptor, how many DISTINCT other-arm pools contain a match
    kept: list[str] = []
    offset = len(flat)
    pool_spans = []
    for p in others:
        pool_spans.append((offset, offset + len(p)))
        offset += len(p)
    for ci, cv in enumerate(cand_vecs):
        support = sum(any(cosine(cv, vecs[t]) >= sim for t in range(a, b)) for a, b in pool_spans)
        if support >= k:
            kept.append(flat[ci])
    return kept


# ---- Phase 4: weak-supervision aggregation + contrastive calibration ---------------------------------
def _dedup(descs: list[str]) -> list[str]:
    """Union with near-duplicate collapse (embedding cosine ≥ _DEDUP_SIM) — one node per distinct concept."""

    seen = [d for d in dict.fromkeys(d.strip() for d in descs if d.strip())]  # exact-dup + order preserve
    if len(seen) < 2:
        return seen
    vecs, _ = embed_texts(seen, resolve_model())
    out: list[str] = []
    out_vecs: list[list[float]] = []
    for d, v in zip(seen, vecs, strict=True):
        if all(cosine(v, ov) < _DEDUP_SIM for ov in out_vecs):
            out.append(d)
            out_vecs.append(v)
    return out


def aggregate_reference(sources: list[list[str]]) -> tuple[list[str], float]:
    """Dedupe noisy reference sources and estimate semantic inter-source agreement."""

    cleaned = [list(dict.fromkeys(d.strip() for d in source if d.strip())) for source in sources]
    nonempty = [source for source in cleaned if source]
    if not nonempty:
        return [], 0.0
    union = _dedup([descriptor for source in nonempty for descriptor in source])
    if len(nonempty) < 2:
        return union, 0.5

    def directed_agreement(left: list[list[float]], right: list[list[float]]) -> float:
        return sum(max(0.0, max(cosine(vector, other) for other in right)) for vector in left) / len(left)

    vectors = [embed_texts(source, resolve_model())[0] for source in nonempty]
    agreements = []
    for i, left in enumerate(vectors):
        for right in vectors[i + 1:]:
            agreements.append((directed_agreement(left, right) + directed_agreement(right, left)) / 2)
    return union, round(sum(agreements) / len(agreements), 4)


def contrastive_score(self_sim: float, negative_sims: list[float], *, temperature: float = 0.1) -> float:
    """InfoNCE-style calibration: the candidate's similarity to ITS OWN brief reference vs to other
    briefs' references (in-batch negatives). Chance floor is 1/(#briefs), preserving VERTEX's
    0-under-chance property without an authored reference. Degenerates to `self_sim` with no negatives."""

    if not negative_sims:
        return self_sim
    import math

    logits = [self_sim, *negative_sims]
    mx = max(logits)
    exps = [math.exp((x - mx) / temperature) for x in logits]
    return round(exps[0] / sum(exps), 4)


# ---- the resolver used per-candidate by score._vertex ------------------------------------------------
def resolve_reference(brief: ProjectBrief, cand: Candidate,
                      mode: str | None = None) -> tuple[list[str], list[str], dict]:
    """(capability_ref, architecture_ref, detail) for the active per-candidate mode. `consensus` needs
    the pool, so per-candidate it resolves to `qe`; full consensus is computed in `score_pool`."""

    mode = resolve_ref_mode(mode)
    authored_cap, authored_arch = brief.capability_descriptors, brief.architecture_anchors
    if mode == "authored":
        return authored_cap, authored_arch, {"ref_mode": "authored"}
    brief_cap, brief_arch = extract_brief_descriptors(brief)
    if mode == "brief":
        return brief_cap, brief_arch, {"ref_mode": "brief"}
    repo_arch = repo_arch_reference()
    if mode == "repo":
        return brief_cap, (repo_arch or brief_arch), {"ref_mode": "repo", "corpus": len(load_arch_corpus())}
    # qe (and per-candidate consensus): weak-supervision aggregate of the architecture sources
    arch_ref, conf = aggregate_reference([brief_arch, repo_arch])
    return brief_cap, (arch_ref or authored_arch), {
        "ref_mode": "qe" if mode != "consensus" else "consensus(per-candidate=qe)",
        # an empty aggregate falls back to the AUTHORED anchors — record it so a "reference-free" run
        # that actually leaned on the authored reference is visible in the runrecord, never silent
        **({"arch_ref_fallback": "authored"} if not arch_ref else {}),
        "arch_confidence": conf, "corpus": len(load_arch_corpus())}


# ---- Phase 5 support: pool-level QE with consensus (validation/aggregate) ----------------------------
def score_pool(brief: ProjectBrief, candidates: list[Candidate]) -> list[dict]:
    """Per-candidate VERTEX-QE over a pool of arms on ONE brief, adding leave-one-out consensus to the
    aggregate reference. Returns a dict per candidate with `vertex_qe` and its parts. In-batch
    contrastive calibration (`contrastive_score`) is NOT applied here: the Track P corpus is a single
    brief, so no cross-brief negatives exist yet — it activates once multi-brief runs land."""

    from ..analysis.vertex import vertex_score
    from ..bootstrap import app_files

    brief_cap, brief_arch = extract_brief_descriptors(brief)
    repo_arch = repo_arch_reference()
    arch_pools = [architecture_descriptors(app_files(c.files)) or c.module_descriptors for c in candidates]
    cap_pools = [c.capabilities for c in candidates]
    out = []
    for i, c in enumerate(candidates):
        cons_arch = consensus_descriptors(arch_pools, i)
        cons_cap = consensus_descriptors(cap_pools, i)
        arch_ref, arch_conf = aggregate_reference([brief_arch, repo_arch, cons_arch])
        cap_ref, _ = aggregate_reference([brief_cap, cons_cap])
        cap_v = vertex_score(cap_pools[i], cap_ref).vertex
        arch_v = vertex_score(arch_pools[i], arch_ref or brief_arch).vertex
        architecture_weight = 0.3 * arch_conf
        qe = round((0.7 * cap_v + architecture_weight * arch_v) / (0.7 + architecture_weight), 4)
        out.append({"harness_id": c.harness_id, "vertex_qe": qe, "capability": cap_v,
                    "architecture": arch_v, "arch_confidence": arch_conf,
                    "consensus_arch": len(cons_arch), "consensus_cap": len(cons_cap)})
    return out
