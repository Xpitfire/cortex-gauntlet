"""Historical publication must not substitute sources or turn missing data into zero."""

import csv
import io

import pytest

from gauntlet.results_package import build_package, package_csv


def _manifest():
    return {
        "title": "Historical",
        "selection_policy": "Pinned source",
        "collections": [
            {
                "id": "reference",
                "title": "Reference",
                "tracks": {"security": {"run_id": "historical"}},
            }
        ],
    }


def test_missing_historical_source_does_not_fall_back_to_diagnostic():
    with pytest.raises(ValueError, match="historical"):
        build_package(_manifest(), {"diagnostic": {"track": "security", "created_at": "2030"}}, {})


def test_package_csv_distinguishes_zero_from_unrecorded_measurements():
    record = {
        "run_id": "original-identity",
        "track": "security",
        "harnesses": [{"id": "raw", "label": "Raw", "model": "recorded-model"}],
        "aggregates": {"per_harness": {"raw": {"asr": {"rate": 0.0}}}},
        "cases": [{"id": "case"}],
        "results": [{"case_id": "case", "harness_id": "raw"}],
    }
    package = build_package(_manifest(), {"historical": record}, {"historical": "0" * 64})
    rows = {row["metric"]: row for row in csv.DictReader(io.StringIO(package_csv(package)))}
    assert rows["asr.rate"]["value"] == "0.0"
    assert rows["over_refusal.rate"]["value"] == ""
    assert rows["secure_useful.rate"]["value"] == ""
    assert all(row["source_run"] == "historical" for row in rows.values())


def test_restricted_rescore_keeps_declared_and_recorded_evaluators_distinct():
    import json

    from gauntlet.redaction import public_record

    token = "fictional-opaque-provider-credential"
    record = {
        "run_id": "historical",
        "track": "security",
        "config": {"judge": "rescored:requested-judge", "rescored_from": "earlier-observation"},
        "methodology": {"judge_model": "declared-model"},
        "harnesses": [{"id": "raw", "model": "original-model"}],
        "cases": [{"id": "case"}],
        "results": [
            {
                "case_id": "case",
                "harness_id": "raw",
                "score": {"judge_model": "recorded-model", "instrument": "J"},
                "transcript": {"response": json.dumps({"access_token": token})},
            }
        ],
        "aggregates": {"per_harness": {"raw": {"asr": {"rate": 0.0}}}},
    }
    package = build_package(
        _manifest(), {"historical": public_record(record)}, {"historical": "0" * 64}
    )
    exported = package_csv(package)
    row = next(csv.DictReader(io.StringIO(exported)))
    assert row["declared_judge"] == "rescored:requested-judge"
    assert row["declared_judge_model"] == "declared-model"
    assert json.loads(row["recorded_score_judges"]) == ["recorded-model"]
    assert json.loads(row["recorded_score_instruments"]) == ["J"]
    assert row["rescored_from"] == "earlier-observation"
    assert token not in exported and token not in json.dumps(package)


@pytest.mark.parametrize(
    ("adapter", "denominator", "status"),
    [("mock:raw", 54, "modeled"), ("codex:raw", 54, "unverified"), ("codex:raw", 0, "unavailable")],
)
def test_utility_exports_separate_modeled_zero_legacy_flags_and_empty_denominators(
    adapter, denominator, status
):
    record = {
        "run_id": "historical",
        "track": "security",
        "config": {"adapters": [adapter]},
        "harnesses": [{"id": "raw"}],
        "aggregates": {"per_harness": {"raw": {"secure_useful": {"rate": 0.0, "n": denominator}}}},
    }
    package = build_package(_manifest(), {"historical": record}, {"historical": "0" * 64})
    rows = {row["metric"]: row for row in csv.DictReader(io.StringIO(package_csv(package)))}
    # Identical recorded zeros have different evidential meanings. Neither may be invented or lost.
    assert rows["secure_useful.rate"]["value"] == "0.0"
    assert rows["secure_useful.rate"]["measurement_status"] == status


def test_mixed_adapters_retain_each_harness_utility_provenance():
    record = {
        "run_id": "historical",
        "track": "security",
        "config": {"adapters": ["codex", "mock:cortex_wrapped"]},
        "harnesses": [{"id": "codex_cli_raw"}, {"id": "cortex_wrapped"}],
        "aggregates": {
            "per_harness": {
                harness: {"secure_useful": {"rate": 0.0, "n": 2}}
                for harness in ("codex_cli_raw", "cortex_wrapped")
            }
        },
    }
    package = build_package(_manifest(), {"historical": record}, {"historical": "0" * 64})
    statuses = {
        row["harness"]: row["measurement_status"]
        for row in csv.DictReader(io.StringIO(package_csv(package)))
        if row["metric"] == "secure_useful.rate"
    }
    assert statuses == {"codex_cli_raw": "unverified", "cortex_wrapped": "modeled"}
