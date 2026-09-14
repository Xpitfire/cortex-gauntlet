"""retry-timeouts: reload a completed Track-S record and re-run ONLY the cells missing from it (the
timed-out ones), merging cleanly and re-aggregating — without re-running the whole suite."""

from gauntlet.run import DEFAULT_ADAPTERS, retry_security_timeouts, run_suite


def test_retry_reruns_only_missing_and_merges():
    rec = run_suite(suite="security", adapter_specs=DEFAULT_ADAPTERS, seeds=1, limit=3).to_dict()
    full = len(rec["results"])
    # simulate two timed-out cells: dropped from results, listed as skipped
    dropped, rec["results"] = rec["results"][:2], rec["results"][2:]
    rec["skipped"] = [{"item": d["case_id"], "harness": d["harness_id"], "reason": "timed out"} for d in dropped]

    rebuilt, retried_ok, still = retry_security_timeouts(rec)

    assert retried_ok == 2 and still == 0          # the two missing cells were re-run; none left skipped
    assert len(rebuilt.results) == full            # merged back to the full grid
    assert rebuilt.aggregates["per_harness"]       # aggregates recomputed over the full set
    assert rebuilt.skipped == []
    assert len(rebuilt.to_dict()["results"]) == full  # serializes cleanly (existing dicts + fresh objects)


def test_retry_is_a_noop_when_nothing_is_missing():
    rec = run_suite(suite="security", adapter_specs=DEFAULT_ADAPTERS, seeds=1, limit=2).to_dict()
    rebuilt, retried_ok, still = retry_security_timeouts(rec)
    assert retried_ok == 0 and still == 0
    assert len(rebuilt.results) == len(rec["results"])
