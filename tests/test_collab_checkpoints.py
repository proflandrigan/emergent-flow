"""
tests/test_collab_checkpoints.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 10 -- checkpoint model and SessionStore primitives
(apply_direct_mutation / revert_checkpoint). Mirrors tests/test_collab_gates.py's
structure and conventions.
"""

from __future__ import annotations

import pytest

from emergentflow.collab.checkpoints import Checkpoint, CheckpointKind
from emergentflow.collab.session import (
    SessionStore,
    StaleVersionError,
    UnknownCheckpointError,
    UnknownSessionError,
)
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation, MutationError
from emergentflow.nodes.examples.load_csv import LoadCsv


def _load_csv_node():
    return LoadCsv().instantiate(path="a.csv")


class TestCheckpointModel:
    def test_defaults(self) -> None:
        node = _load_csv_node()
        cp = Checkpoint(
            kind=CheckpointKind.EDIT,
            base_version=0,
            mutation=GraphMutation(base_version=0, add_nodes=[node]),
            previous_graph=Graph(),
            resulting_version=1,
        )
        assert cp.id is not None
        assert cp.author == "agent"
        assert cp.description == ""
        assert cp.timestamp > 0

    def test_round_trips_through_json(self) -> None:
        node = _load_csv_node()
        cp = Checkpoint(
            kind=CheckpointKind.REVERT,
            author="agent-x",
            description="Revert: add node",
            base_version=1,
            mutation=GraphMutation(base_version=1, add_nodes=[node]),
            previous_graph=Graph(),
            resulting_version=2,
        )
        dumped = cp.model_dump(mode="json")
        restored = Checkpoint.model_validate(dumped)
        assert restored == cp


class TestApplyDirectMutation:
    def test_applies_mutation_bumps_version_and_creates_edit_checkpoint(self) -> None:
        store = SessionStore()
        session = store.create()
        q = store.subscribe(session.id)
        node = _load_csv_node()
        mutation = GraphMutation(base_version=0, add_nodes=[node], description="add a csv node")

        result_session, checkpoint = store.apply_direct_mutation(
            session.id, mutation, author="agent-x"
        )

        assert result_session.version == 1
        assert node.id in result_session.graph.nodes
        assert checkpoint.kind == CheckpointKind.EDIT
        assert checkpoint.author == "agent-x"
        assert checkpoint.description == "add a csv node"
        assert checkpoint.base_version == 0
        assert checkpoint.resulting_version == 1
        assert checkpoint.previous_graph == Graph()
        assert result_session.collab.checkpoints[checkpoint.id] is checkpoint

        event = q.get(timeout=1.0)
        assert event == {
            "type": "graph_changed",
            "session_id": session.id,
            "version": 1,
            "checkpoint_id": checkpoint.id,
            "author": "agent-x",
            "description": "add a csv node",
        }

    def test_raises_stale_version_on_mismatch(self) -> None:
        store = SessionStore()
        session = store.create()
        node = _load_csv_node()
        mutation = GraphMutation(base_version=5, add_nodes=[node])

        with pytest.raises(StaleVersionError):
            store.apply_direct_mutation(session.id, mutation)

    def test_raises_mutation_error_for_invalid_mutation(self) -> None:
        store = SessionStore()
        session = store.create()
        mutation = GraphMutation(base_version=0, remove_nodes=["does-not-exist"])

        with pytest.raises(MutationError):
            store.apply_direct_mutation(session.id, mutation)

    def test_raises_unknown_session(self) -> None:
        store = SessionStore()
        mutation = GraphMutation(base_version=0)
        with pytest.raises(UnknownSessionError):
            store.apply_direct_mutation("no-such-session", mutation)


class TestRevertCheckpoint:
    def test_revert_restores_prior_graph_bumps_version_and_creates_revert_checkpoint(
        self,
    ) -> None:
        store = SessionStore()
        session = store.create()
        node = _load_csv_node()
        mutation = GraphMutation(base_version=0, add_nodes=[node])
        _, edit_checkpoint = store.apply_direct_mutation(session.id, mutation)
        assert node.id in store.get(session.id).graph.nodes

        q = store.subscribe(session.id)
        result_session = store.revert_checkpoint(session.id, edit_checkpoint.id)

        assert result_session.version == 2
        assert node.id not in result_session.graph.nodes
        revert = result_session.collab.checkpoints[
            next(
                cid
                for cid, cp in result_session.collab.checkpoints.items()
                if cp.kind == CheckpointKind.REVERT
            )
        ]
        assert revert.kind == CheckpointKind.REVERT
        assert revert.author == edit_checkpoint.author
        assert revert.description == f"Revert: {edit_checkpoint.description}"
        assert revert.base_version == 1
        assert revert.resulting_version == 2
        assert revert.previous_graph is not None

        event = q.get(timeout=1.0)
        assert event == {
            "type": "graph_reverted",
            "session_id": session.id,
            "version": 2,
            "checkpoint_id": revert.id,
            "reverted_checkpoint_id": edit_checkpoint.id,
            "author": revert.author,
            "description": revert.description,
        }

    def test_revert_unknown_checkpoint_raises(self) -> None:
        store = SessionStore()
        session = store.create()
        with pytest.raises(UnknownCheckpointError):
            store.revert_checkpoint(session.id, "no-such-checkpoint")

    def test_revert_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.revert_checkpoint("no-such-session", "whatever")
