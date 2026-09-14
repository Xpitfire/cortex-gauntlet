"""Graded patch-quality scoring for Track R — turn a binary "hidden test passes" into a composite.

Mirrors the SWE-bench design (Resolution × Maintenance) and the patch-quality literature: a good fix
is correct (FAIL_TO_PASS), robust on held-out cases it never saw (anti-overfit), regression-safe
(PASS_TO_PASS), localized (F1 vs the gold edit set), and minimal (not bloated vs the gold diff). Tests
the arm tries to EDIT are stripped before grading (the SWE-bench anti-cheat) and flagged.

All functions are pure (no IO) so they unit-test without running anything.
"""

from __future__ import annotations

import difflib
import re

# a path that is a test/grader file — the arm must NOT satisfy a task by editing tests (anti-cheat)
_TEST_PATH = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|conftest\.py)$|(^|/)tests?/")


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def extract_patch(base: dict[str, str], overlay: dict[str, str]) -> dict[str, str]:
    """Files the arm added or changed relative to the base repo (deletions are not modelled here)."""
    return {p: c for p, c in overlay.items() if base.get(p) != c}


def sanitize_patch(patch: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Drop any test-file edits from the arm's patch (graded against OUR hidden tests only); return the
    code-only patch + the stripped test paths (a non-empty list is a cheat attempt)."""
    code = {p: c for p, c in patch.items() if not is_test_path(p)}
    stripped = [p for p in patch if is_test_path(p)]
    return code, stripped


def changed_line_count(base: dict[str, str], files: dict[str, str]) -> int:
    """Total added+removed source lines of `files` vs `base` (unified-diff +/- lines, excluding hunks)."""
    total = 0
    for path in set(base) | set(files):
        before = (base.get(path) or "").splitlines()
        after = (files.get(path) or "").splitlines()
        for line in difflib.unified_diff(before, after, lineterm=""):
            if line[:1] in "+-" and line[:3] not in ("+++", "---"):
                total += 1
    return total


def locality_f1(changed_paths: set[str], expected_paths: set[str]) -> float:
    """F1 of the files the arm touched vs the files the gold fix touches (1.0 = exact-location agreement);
    penalizes shotgun edits (precision) and missing the right place (recall)."""
    if not changed_paths and not expected_paths:
        return 1.0
    hit = len(changed_paths & expected_paths)
    if hit == 0:
        return 0.0
    precision = hit / len(changed_paths)
    recall = hit / len(expected_paths) if expected_paths else 1.0
    return round(2 * precision * recall / (precision + recall), 4)


def minimality(arm_lines: int, gold_lines: int) -> float:
    """1.0 when the patch is as tight as (or tighter than) the gold diff; decays as it bloats."""
    if arm_lines <= gold_lines or arm_lines <= 0:
        return 1.0
    return round(max(0.0, gold_lines) / arm_lines, 4) if gold_lines else round(1.0 / arm_lines, 4)


# composite weights (over a RESOLVED patch): robustness dominates (anti-overfit is the real signal),
# then regression safety, then the patch-quality channels. A cheat zeroes it. Sums to 1.0.
_W = {"robustness": 0.40, "regression": 0.25, "minimality": 0.15, "locality": 0.10, "code_health": 0.10}


def composite(*, resolved: bool, robustness: float, regression: float, minimality_score: float,
              locality: float, code_health: float, cheated: bool) -> float:
    """Graded quality-of-fix in [0,1]: 0 if the shown test fails or the arm cheated, else the weighted
    blend of the robustness/regression/minimality/locality/health axes."""
    if not resolved or cheated:
        return 0.0
    score = (_W["robustness"] * robustness + _W["regression"] * regression
             + _W["minimality"] * minimality_score + _W["locality"] * locality
             + _W["code_health"] * code_health)
    return round(score, 4)
