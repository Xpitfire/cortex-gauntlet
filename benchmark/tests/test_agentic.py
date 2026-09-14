"""Agentic hard tier: a curated set of prepared-workspace injection cases that DISCRIMINATE harnesses
— a benign carrier task plus an injection planted in a file the agent reads (the workspace also holds a
decoy `.env` whose API_TOKEN is the canary). This replaces the saturated direct-exfil matrix everyone
refused. See agentic_corpus.py and docs/agentic-redesign-research.md."""

from gauntlet.cases import load_security_suite
from gauntlet.enums import Modality, Objective
from gauntlet.run import build_adapter, build_judge, score_case

AGENTIC = [c for c in load_security_suite("security") if c.family.startswith("agentic_")]


def test_curated_agentic_cases_with_prepared_environments():
    for c in AGENTIC:
        # the injection lives in a workspace file (or, for vision/audio cases, the rendered asset)
        assert c.workspace_files or c.modality in (Modality.IMAGE, Modality.AUDIO), c.id
        assert c.payload, c.id  # the injection text — used for echo-filtering in the judge
        # the carrier instruction is BENIGN; the secret ask lives only in the planted file/asset
        assert "API_TOKEN" not in c.instruction, c.id


def test_agentic_tier_spans_all_three_harmful_objectives():
    objs = {c.objective for c in AGENTIC}
    assert objs == {Objective.SECRET_EXFIL, Objective.MALICIOUS_DEP, Objective.DESTRUCTIVE_GIT}


def test_agentic_tier_discriminates_harnesses_in_mock():
    judge = build_judge("heuristic")
    rate = {a: sum(score_case(c, build_adapter(a), judge, 3).complies > 0 for c in AGENTIC)
            for a in ("mock:codex_cli_raw", "mock:cortex_wrapped")}
    # a spread, not floor/ceiling: the governed arm resists more than raw codex, and raw isn't at 0
    assert rate["mock:cortex_wrapped"] < rate["mock:codex_cli_raw"]
    assert rate["mock:codex_cli_raw"] > 0
