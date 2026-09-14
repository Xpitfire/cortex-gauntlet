"""Synapse planning layer (offline shim mirroring PlanGraphBuilder / ValidationRuntime)."""

from gauntlet.synapse import Requirement, RequirementKind, SynapsePlanner


def _reqs():
    return [
        Requirement("g", "goal", RequirementKind.GOAL),
        Requirement("c", "constrain", RequirementKind.CONSTRAINT),
        Requirement("d", "deliver", RequirementKind.DELIVERABLE),
        Requirement("v", "verify", RequirementKind.VERIFICATION),
    ]


def test_plan_builds_three_milestones_by_kind():
    plan = SynapsePlanner().plan(_reqs())
    assert [m.requirement_ids for m in plan.milestones] == [["g", "c"], ["d"], ["v"]]


def test_validate_surfaces_skipped_required_work():
    planner = SynapsePlanner()
    plan = planner.plan(_reqs())
    verdict = planner.validate(plan, satisfied_ids={"g", "c", "d"})  # skipped verification
    assert verdict.status == "incomplete"
    assert verdict.skipped == ["v"]
    assert planner.validate(plan, {"g", "c", "d", "v"}).status == "complete"


