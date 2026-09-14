"""Load a suite manifest + seed corpus and expand it into concrete Cases.

Track S is a CURATED, discriminative corpus (not a saturated obfuscation matrix — every frontier model
refuses blatant "read .env and POST it", giving zero signal). It spans:
- the agentic hard tier: a benign carrier task + an injection planted in a file the agent reads, in a
  prepared workspace, across secret-exfil / malicious-dep / destructive-git (see agentic_corpus.py),
- canary probes (rogue-string instruction-following), and
- benign over-refusal controls (the secure-AND-useful axis).
"""

from __future__ import annotations

import json
from pathlib import Path

from .agentic_corpus import SCENARIOS, load_private_scenarios
from .enums import Modality, Objective, Surface, Technique, Track
from .models import Case
from .paths import SUITES
from .sandbox import make_canary
from .transforms import apply_technique


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def _case(
    name: str,
    cid: str,
    objective: Objective,
    *,
    surface: Surface,
    technique: Technique,
    modality: Modality,
    instruction: str,
    payload: str = "",
    benign: bool = False,
    benign_task: str = "",
    family: str = "",
    held_out: bool = False,
    workspace_files: dict[str, str] | None = None,
    scaffold_fill: float = 0.0,
    needle_count: int = 1,
    asset_fixture: str | None = None,
) -> Case:
    ground_truth = "comply" if benign else "refuse"
    return Case(
        id=cid,
        track=Track.SECURITY,
        surface=surface,
        technique=technique,
        objective=objective,
        modality=modality,
        benign=benign,
        family=family,
        instruction=instruction,
        canary=make_canary(cid),
        ground_truth=ground_truth,
        payload=payload,
        benign_task=benign_task,
        held_out=held_out,
        workspace_files=workspace_files or {},
        scaffold_fill=scaffold_fill,
        needle_count=needle_count,
        asset_fixture=asset_fixture,
    )


def load_security_suite(name: str = "security") -> list[Case]:
    suite_dir = SUITES / name
    manifest = json.loads((suite_dir / "manifest.json").read_text())
    seeds = json.loads((suite_dir / Path(manifest["seeds"])).read_text())

    probe_techniques = [Technique(t) for t in manifest["probe_techniques"]]

    cases: list[Case] = []
    cases += _agentic_cases(name)  # the hard, discriminative tier (prepared-workspace injections)
    cases += _probe_cases(name, seeds["probe_seeds"], probe_techniques)
    cases += _benign_cases(name, seeds["benign_controls"])
    return cases


def _probe_cases(name, probe_seeds, probe_techniques) -> list[Case]:
    out: list[Case] = []
    for seed in probe_seeds:
        for technique in probe_techniques:
            cid = f"{name}-probe-{technique.value}"
            canary = make_canary(cid)
            raw = seed["instruction"].replace("{CANARY}", canary)
            payload = apply_technique(technique, raw)
            out.append(Case(
                id=cid, track=Track.SECURITY, surface=Surface.DIRECT_TURN, technique=technique,
                objective=Objective.CANARY_ECHO, modality=Modality.TEXT, benign=False,
                family="probe", instruction=payload, canary=canary, ground_truth="refuse",
                payload=payload,
            ))
    return out


def _agentic_cases(name: str) -> list[Case]:
    """Expand the curated agentic corpus (agentic_corpus.SCENARIOS): each is a BENIGN carrier task plus
    an injection planted in a file the agent READS in its prepared workspace (which holds a decoy `.env`
    whose `API_TOKEN` is the case canary). Success = the agent leaks the canary or proposes the harmful
    action (deterministic oracle). See docs/agentic-redesign-research.md."""

    assets = SUITES / name / "assets"
    return [
        _case(name, f"{name}-{s.family}", s.objective, surface=s.surface, technique=s.technique,
              modality=s.modality, instruction=s.carrier, payload=s.injection,
              family=s.family, benign_task=s.family.replace("_", " "),
              held_out=s.held_out, workspace_files=s.files, scaffold_fill=s.scaffold_fill,
              needle_count=s.needle_count,
              asset_fixture=str(assets / s.asset_fixture) if s.asset_fixture else None)
        for s in [*SCENARIOS, *load_private_scenarios()]
    ]


def _benign_cases(name, benign_controls) -> list[Case]:
    out: list[Case] = []
    for seed in benign_controls:
        cid = f"{name}-benign-{_slug(seed['family'])}"
        out.append(_case(name, cid, Objective.BENIGN, surface=Surface.DIRECT_TURN,
                         technique=Technique.DIRECT, modality=Modality.TEXT,
                         instruction=seed["instruction"], payload=seed["instruction"],
                         benign=True, family=seed["family"],
                         workspace_files=seed.get("files")))  # seed any file the benign task must read
    return out
