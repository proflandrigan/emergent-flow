"""
tests/test_collab_tours_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Guided tours (issue #171) -- SessionStore tour CRUD, tour_* events, anchor validation, and the
ADR 0019 invariant that tour writes never touch the graph, version, or checkpoints.
"""

from __future__ import annotations

import queue
from typing import Any

import pytest

from emergentflow.collab.session import (
    DuplicateTourError,
    SessionStore,
    UnknownSessionError,
    UnknownTourError,
)
from emergentflow.collab.tours import Tour, TourAnchorError, TourStep
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.ir.port import Port


def _node(node_id: str) -> Node:
    port = Port(id=f"{node_id}p", name="frame", direction=Direction.OUT, data_type="DataFrame")
    return Node(id=node_id, type="data.load_csv", ports=[port])


def _graph(*ids: str) -> Graph:
    return Graph(nodes={i: _node(i) for i in ids}, edges={})


def _tour(tour_id: str = "t1", *nodes: str, title: str = "T") -> Tour:
    focus = list(nodes) or ["n1"]
    return Tour(
        id=tour_id,
        title=title,
        conclusion="C",
        author="a",
        steps=[TourStep(focus=focus, note="look")],
    )


def _drain(q: queue.SimpleQueue[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        try:
            events.append(q.get_nowait())
        except queue.Empty:
            return events


def _setup() -> tuple[SessionStore, str, queue.SimpleQueue[dict[str, Any]]]:
    store = SessionStore()
    session = store.create(_graph("n1", "n2"))
    return store, session.id, store.subscribe(session.id)


def test_create_and_list() -> None:
    store, sid, q = _setup()
    tour = Tour(title="T", conclusion="C", author="a", steps=[TourStep(focus=["n1"], note="look")])
    created = store.create_tour(sid, tour)
    assert created.id == tour.id
    assert [t.id for t in store.list_tours(sid)] == [tour.id]
    assert [e["type"] for e in _drain(q)] == ["tour_added"]


def test_create_duplicate_raises_and_leaves_state() -> None:
    store, sid, q = _setup()
    store.create_tour(sid, _tour("t1", title="first"))
    _drain(q)
    with pytest.raises(DuplicateTourError):
        store.create_tour(sid, _tour("t1", title="second"))
    assert _drain(q) == []
    assert [t.title for t in store.list_tours(sid)] == ["first"]


def test_replace_absent_and_present() -> None:
    store, sid, q = _setup()
    with pytest.raises(UnknownTourError):
        store.replace_tour(sid, _tour("t1"))
    assert _drain(q) == []
    store.create_tour(sid, _tour("t1", title="old"))
    _drain(q)
    store.replace_tour(sid, _tour("t1", title="new"))
    assert [t.title for t in store.list_tours(sid)] == ["new"]
    assert [e["type"] for e in _drain(q)] == ["tour_updated"]


def test_upsert_twice_keeps_one_tour() -> None:
    store, sid, q = _setup()
    store.upsert_tour(sid, _tour("t1", title="a"))
    store.upsert_tour(sid, _tour("t1", title="b"))
    assert [t.title for t in store.list_tours(sid)] == ["b"]
    assert [e["type"] for e in _drain(q)] == ["tour_added", "tour_updated"]


def test_anchor_failure_leaves_state_and_events_untouched() -> None:
    store, sid, q = _setup()
    tour = Tour(
        id="t1",
        title="T",
        conclusion="C",
        author="a",
        steps=[
            TourStep(focus=["n1", "gone0"], note="x"),
            TourStep(route=("n2", "gone1"), note="y"),
        ],
    )
    with pytest.raises(TourAnchorError) as info:
        store.create_tour(sid, tour)
    assert info.value.missing == [(0, "gone0"), (1, "gone1")]
    assert store.get(sid).collab.tours == {}
    assert _drain(q) == []


def test_delete_and_missing() -> None:
    store, sid, q = _setup()
    store.create_tour(sid, _tour("t1"))
    _drain(q)
    store.delete_tour(sid, "t1")
    assert store.list_tours(sid) == []
    assert [e["type"] for e in _drain(q)] == ["tour_deleted"]
    with pytest.raises(UnknownTourError):
        store.delete_tour(sid, "t1")


def test_unknown_session_for_every_method() -> None:
    store = SessionStore()
    with pytest.raises(UnknownSessionError):
        store.create_tour("nope", _tour())
    with pytest.raises(UnknownSessionError):
        store.replace_tour("nope", _tour())
    with pytest.raises(UnknownSessionError):
        store.upsert_tour("nope", _tour())
    with pytest.raises(UnknownSessionError):
        store.list_tours("nope")
    with pytest.raises(UnknownSessionError):
        store.delete_tour("nope", "t1")


def test_list_sorted_by_id() -> None:
    store, sid, _ = _setup()
    for tid in ("b", "a", "c"):
        store.create_tour(sid, _tour(tid))
    assert [t.id for t in store.list_tours(sid)] == ["a", "b", "c"]


def test_returned_objects_are_copies() -> None:
    store, sid, _ = _setup()
    returned = store.create_tour(sid, _tour("t1", title="orig"))
    returned.title = "mutated"
    listed = store.list_tours(sid)[0]
    listed.title = "mutated too"
    assert store.list_tours(sid)[0].title == "orig"


def test_tour_writes_do_not_touch_graph_version_or_checkpoints() -> None:
    store, sid, _ = _setup()
    session = store.get(sid)
    before = session.graph.model_dump_json()
    version = session.version
    checkpoint_keys = set(session.collab.checkpoints)
    store.create_tour(sid, _tour("t1"))
    store.replace_tour(sid, _tour("t1", title="x"))
    store.delete_tour(sid, "t1")
    after = store.get(sid)
    assert after.graph.model_dump_json() == before
    assert after.version == version
    assert set(after.collab.checkpoints) == checkpoint_keys


def test_stale_tour_is_kept_but_cannot_be_rewritten() -> None:
    store, sid, _ = _setup()
    store.create_tour(sid, _tour("t1", "n1"))
    store.replace_graph(sid, _graph("n2"), expected_version=store.get(sid).version)
    assert [t.id for t in store.list_tours(sid)] == ["t1"]
    assert store.list_tours(sid)[0].steps[0].focus == ["n1"]
    with pytest.raises(TourAnchorError):
        store.replace_tour(sid, _tour("t1", "n1"))
    assert store.list_tours(sid)[0].steps[0].focus == ["n1"]
