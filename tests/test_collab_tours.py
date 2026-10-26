"""
tests/test_collab_tours.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Guided tours (issue #171) -- Tour/TourStep models, shared anchor helpers, and the
``CollaborationState.tours`` field. No SessionStore/HTTP surface yet.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from pydantic import ValidationError

import emergentflow.collab.anchors as anchors_module
from emergentflow.collab.anchors import AnchorError, missing_node_ids
from emergentflow.collab.review import AnchorError as ReviewAnchorError
from emergentflow.collab.review import CollaborationState
from emergentflow.collab.tours import (
    Tour,
    TourAnchorError,
    TourStep,
    step_anchor_ids,
    validate_tour_anchors,
)
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.ir.port import Port


def _graph() -> Graph:
    nodes = {
        nid: Node(
            id=nid,
            type="data.load_csv",
            ports=[
                Port(id=f"p_{nid}", name="frame", direction=Direction.OUT, data_type="DataFrame")
            ],
        )
        for nid in ("n1", "n2", "n3")
    }
    return Graph(nodes=nodes, edges={})


def _step(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"note": "a note"}
    base.update(kw)
    return base


def _tour(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "T",
        "conclusion": "C",
        "author": "agent",
        "steps": [_step(focus=["n1"])],
    }
    base.update(kw)
    return base


def test_issue_example_validates() -> None:
    tour = Tour.model_validate(
        _tour(
            steps=[
                _step(focus=["n1"]),
                _step(focus=["n2"], reach="down"),
                _step(route=["n1", "n3"], unknowns=["is n2 needed?"]),
            ]
        )
    )
    assert len(tour.steps) == 3
    assert tour.steps[1].reach == "down"
    assert tour.steps[2].route == ("n1", "n3")


def test_default_id_and_extra_forbidden() -> None:
    tour = Tour.model_validate(_tour())
    assert tour.id
    with pytest.raises(ValidationError):
        Tour.model_validate(_tour(bogus=1))
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1"], bogus=1))


def test_blank_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Tour.model_validate(_tour(id="  "))


@pytest.mark.parametrize("field", ["title", "conclusion", "author"])
@pytest.mark.parametrize("value", ["", "   "])
def test_blank_tour_text_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Tour.model_validate(_tour(**{field: value}))


@pytest.mark.parametrize("value", ["", "  \n"])
def test_blank_note_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1"], note=value))


def test_stored_text_not_stripped() -> None:
    tour = Tour.model_validate(_tour(title="  padded  "))
    assert tour.title == "  padded  "


def test_step_count_limits() -> None:
    with pytest.raises(ValidationError):
        Tour.model_validate(_tour(steps=[]))
    with pytest.raises(ValidationError):
        Tour.model_validate(_tour(steps=[_step(focus=["n1"])] * 101))
    Tour.model_validate(_tour(steps=[_step(focus=["n1"])] * 100))


@pytest.mark.parametrize(
    "kw",
    [
        {"route": ["n1", "n2"], "focus": ["n1"]},
        {"route": ["n1", "n2"], "reach": "up"},
        {"reach": "up"},
        {},
    ],
)
def test_bad_step_shape_rejected(kw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(**kw))


def test_focus_rules() -> None:
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1", "n1"]))
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1", " "]))
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=[f"n{i}" for i in range(51)]))
    TourStep.model_validate(_step(focus=[f"n{i}" for i in range(50)]))


def test_route_endpoints_non_blank() -> None:
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(route=["n1", " "]))
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(route=["", "n1"]))


def test_unknowns_rules() -> None:
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1"], unknowns=["  "]))
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1"], unknowns=["x" * 1001]))
    with pytest.raises(ValidationError):
        TourStep.model_validate(_step(focus=["n1"], unknowns=["u"] * 21))
    TourStep.model_validate(_step(focus=["n1"], unknowns=["x" * 1000] * 20))


def test_missing_node_ids_order_and_dedup() -> None:
    graph = _graph()
    assert missing_node_ids(graph, ["zz", "n1", "yy", "zz"]) == ["zz", "yy"]


def test_step_anchor_ids() -> None:
    assert step_anchor_ids(TourStep.model_validate(_step(focus=["n1", "n2"]))) == ["n1", "n2"]
    assert step_anchor_ids(TourStep.model_validate(_step(route=["n1", "n3"]))) == ["n1", "n3"]


def test_validate_tour_anchors_ok() -> None:
    tour = Tour.model_validate(_tour(steps=[_step(focus=["n1", "n2"]), _step(route=["n1", "n3"])]))
    validate_tour_anchors(_graph(), tour)


def test_validate_tour_anchors_reports_all_missing() -> None:
    tour = Tour.model_validate(
        _tour(
            steps=[
                _step(focus=["n1", "ghost1"]),
                _step(focus=["n2"]),
                _step(route=["n3", "ghost2"]),
                _step(focus=["ghost3"]),
            ]
        )
    )
    with pytest.raises(TourAnchorError) as exc_info:
        validate_tour_anchors(_graph(), tour)
    err = exc_info.value
    assert isinstance(err, AnchorError)
    assert err.missing == [(0, "ghost1"), (2, "ghost2"), (3, "ghost3")]
    assert err.details() == [
        {"step": 0, "node_id": "ghost1"},
        {"step": 2, "node_id": "ghost2"},
        {"step": 3, "node_id": "ghost3"},
    ]
    assert "ghost1" in str(err)


def test_collaboration_state_tours_round_trip() -> None:
    state = CollaborationState()
    assert state.tours == {}
    tour = Tour.model_validate(_tour())
    state.tours[tour.id] = tour
    restored = CollaborationState.model_validate(state.model_dump(mode="json"))
    assert restored.tours == {tour.id: tour}


def test_anchor_error_reexported_from_review() -> None:
    assert ReviewAnchorError is anchors_module.AnchorError


def test_shared_sample_payload_validates() -> None:
    """The shared sample tour payload (also consumed by UI tests) validates as a Tour."""
    import json

    fixture = pathlib.Path(__file__).parent / "fixtures" / "tour_sample.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    tour = Tour.model_validate(payload)
    assert tour.id == "tour-1"
    assert len(tour.steps) == 3
