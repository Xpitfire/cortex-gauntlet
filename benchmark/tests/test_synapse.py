"""Synapse planning layer (offline shim mirroring PlanGraphBuilder / ValidationRuntime)."""

from gauntlet.synapse import Requirement, RequirementKind, SynapsePlanner, synapse_available


def _reqs():
    return [
        Requirement("g", "goal", RequirementKind.GOAL),
        Requirement("c", "constrain", RequirementKind.CONSTRAINT),
        Requirement("d", "deliver", RequirementKind.DELIVERABLE),
        Requirement("v", "verify", RequirementKind.VERIFICATION),
    ]


def test_plan_builds_three_milestones_by_kind():
    plan = SynapsePlanner().plan(_reqs())
    titles = [m.title for m in plan.milestones]
    assert titles == ["Understand and constrain", "Deliver required work", "Validate and hand off"]
    assert plan.milestones[2].requirement_ids == ["v"]


def test_validate_surfaces_skipped_required_work():
    planner = SynapsePlanner()
    plan = planner.plan(_reqs())
    verdict = planner.validate(plan, satisfied_ids={"g", "c", "d"})  # skipped verification
    assert verdict.status == "incomplete"
    assert verdict.skipped == ["v"]
    assert planner.validate(plan, {"g", "c", "d", "v"}).status == "complete"


def test_backend_label_reflects_availability():
    backend = SynapsePlanner().backend
    assert backend in ("synapse", "shim")
    assert (backend == "synapse") == synapse_available()
