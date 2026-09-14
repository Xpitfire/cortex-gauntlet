"""Track-P WorkflowDAG demonstration (additive, hermetic — no Docker / network / codegen).

Asserts the new `build_workflow_dag` / `workflow_dag_view` helpers produce the expected topological
layering over STOREFRONT_REQUIREMENTS (understand -> deliver -> validate, with the independent
deliverables sharing one parallel layer) and that this trail does NOT change observe_requirements or
the milestone/scoring inputs.
"""

from __future__ import annotations

import pytest

pytest.importorskip("synapse.domain.requirements")

from gauntlet.project.synapse_build import (
    STOREFRONT_REQUIREMENTS,
    build_workflow_dag,
    observe_requirements,
    workflow_dag_view,
)


def _phase_ids(kinds: set[str]) -> set[str]:
    return {r.id for r in STOREFRONT_REQUIREMENTS if r.kind in kinds}


def test_dag_layers_are_understand_then_deliver_then_validate() -> None:
    """Kahn layers follow the phase order; each layer is exactly its phase's requirements."""

    layers = build_workflow_dag().topological_layers()
    assert len(layers) == 3
    assert set(layers[0]) == _phase_ids({"GOAL", "CONSTRAINT"})  # understand / constrain
    assert set(layers[1]) == _phase_ids({"DELIVERABLE"})  # deliver
    assert set(layers[2]) == _phase_ids({"VERIFICATION"})  # validate, strictly last
    # validate depends on deliver depends on understand -> no overlap between layers.
    assert set(layers[0]).isdisjoint(layers[1])
    assert set(layers[1]).isdisjoint(layers[2])


def test_dag_is_acyclic_and_covers_every_requirement() -> None:
    dag = build_workflow_dag()
    assert not dag.has_cycle()
    assert len(dag.nodes) == len(STOREFRONT_REQUIREMENTS)
    covered = {req_id for layer in dag.topological_layers() for req_id in layer}
    assert covered == {r.id for r in STOREFRONT_REQUIREMENTS}


def test_deliverables_share_one_parallel_layer() -> None:
    """The multiple independent deliverables collapse into a single parallel work-unit layer."""

    view = workflow_dag_view()
    deliverables = _phase_ids({"DELIVERABLE"})
    assert len(deliverables) > 1  # there must be several to demonstrate parallelism
    deliver_layer = next(
        layer for layer in view["layers"] if set(layer["requirement_ids"]) == deliverables
    )
    assert deliver_layer["parallel"] is True
    assert set(view["parallel_requirement_ids"]) >= deliverables
    # the single VERIFICATION layer is not parallel.
    verify = _phase_ids({"VERIFICATION"})
    verify_layer = next(
        layer for layer in view["layers"] if set(layer["requirement_ids"]) == verify
    )
    assert verify_layer["parallel"] is False
    assert view["n_nodes"] == len(STOREFRONT_REQUIREMENTS)


def test_workflow_view_does_not_change_observation_or_requirements() -> None:
    """The DAG trail is purely inspectable: observe_requirements and the req set are unchanged."""

    before_ids = [r.id for r in STOREFRONT_REQUIREMENTS]
    before_observe = observe_requirements({"web/index.html": "<html>cart checkout stripe</html>"})

    workflow_dag_view()  # building the DAG view must have no side effects

    assert [r.id for r in STOREFRONT_REQUIREMENTS] == before_ids
    assert observe_requirements({"web/index.html": "<html>cart checkout stripe</html>"}) == (
        before_observe
    )
    assert observe_requirements({}) == set()  # empty repo evidences nothing
