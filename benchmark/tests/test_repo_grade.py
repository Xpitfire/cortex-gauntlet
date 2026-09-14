"""Graded Track-R judge: patch-quality units + good-vs-overfit-vs-cheat integration."""

from gauntlet.livegen.models import CodeGenResult
from gauntlet.repo import grade
from gauntlet.repo.corpus import load_repo_tasks
from gauntlet.repo.score import score_repo_task
from gauntlet.run import PRESETS


# ---- pure units --------------------------------------------------------------
def test_sanitize_strips_test_edits_and_flags_cheat():
    code, stripped = grade.sanitize_patch({"pkg/x.py": "fix", "tests/test_x.py": "evil", "test_y.py": "evil"})
    assert code == {"pkg/x.py": "fix"}
    assert set(stripped) == {"tests/test_x.py", "test_y.py"}


def test_locality_f1_rewards_exact_location():
    assert grade.locality_f1({"a.py"}, {"a.py"}) == 1.0
    assert grade.locality_f1({"a.py", "b.py"}, {"a.py"}) < 1.0       # collateral edit lowers precision
    assert grade.locality_f1({"z.py"}, {"a.py"}) == 0.0


def test_minimality_penalizes_bloat_but_not_tightness():
    assert grade.minimality(2, 2) == 1.0
    assert grade.minimality(1, 2) == 1.0          # smaller than gold is fine
    assert grade.minimality(8, 2) == 0.25         # 4x the gold diff


def test_composite_gates_on_resolution_and_cheat():
    kw = dict(robustness=1.0, regression=1.0, minimality_score=1.0, locality=1.0, code_health=1.0)
    assert grade.composite(resolved=True, cheated=False, **kw) == 1.0
    assert grade.composite(resolved=False, cheated=False, **kw) == 0.0   # unresolved -> 0
    assert grade.composite(resolved=True, cheated=True, **kw) == 0.0     # cheat -> 0


# ---- integration: good fix vs overfit vs cheat -------------------------------
class _Fixed:
    def __init__(self, meta, files):
        self.meta = meta
        self._files = files

    def generate(self, request):
        return CodeGenResult(self.meta.id, "", files=dict(self._files), ok=True)


def _task(tid):
    return next(t for t in load_repo_tasks() if t.id == tid)


def test_good_fix_is_strict_resolved():
    task = _task("bill-split")
    res = score_repo_task(task, PRESETS["codex_cli_raw"], _Fixed(PRESETS["codex_cli_raw"], task.fix_files))
    assert res.resolved and res.strict_resolved and not res.cheated
    assert res.robustness == 1.0 and res.regression == 1.0 and res.composite > 0.9


def test_overfit_patch_resolves_but_fails_held_out():
    task = _task("bill-split")
    overfit = {"billing/split.py": (
        "def split_bill(total_cents, n):\n"
        "    if total_cents == 100 and n == 3:\n"
        "        return [34, 33, 33]\n"
        "    return [total_cents // n] * n\n")}
    res = score_repo_task(task, PRESETS["codex_cli_raw"], _Fixed(PRESETS["codex_cli_raw"], overfit))
    assert res.resolved is True            # passes the SHOWN hidden test
    assert res.strict_resolved is False    # but held-out anti-overfit tests fail
    assert res.robustness < 1.0
    assert res.composite < 0.9


def test_editing_a_test_file_is_caught_as_cheating():
    task = _task("bill-split")
    patch = {**task.fix_files, "tests/test_split.py": "def test_pass(): assert True\n"}
    res = score_repo_task(task, PRESETS["codex_cli_raw"], _Fixed(PRESETS["codex_cli_raw"], patch))
    assert res.cheated is True
    assert res.composite == 0.0 and res.strict_resolved is False
