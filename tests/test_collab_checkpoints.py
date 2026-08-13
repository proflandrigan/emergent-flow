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

    def test_revert_checkpoint_mutation_is_the_faithful_inverse(self) -> None:
        """The REVERT checkpoint's mutation must undo the forward edit.

        For a set_params forward edit, the stored inverse must restore the ORIGINAL
        (pre-edit) param value -- not re-record the forward value. The inverse must be
        derived against the checkpoint's pre-mutation graph snapshot.
        """
        store = SessionStore()
        session = store.create()
        node = _load_csv_node()
        add = GraphMutation(base_version=0, add_nodes=[node])
        _, _ = store.apply_direct_mutation(session.id, add)
        setp = GraphMutation(
            base_version=1, set_params={node.id: {"path": "changed.csv"}}, author="agent"
        )
        _, edit_cp = store.apply_direct_mutation(session.id, setp)

        result = store.revert_checkpoint(session.id, edit_cp.id)
        revert = next(
            cp for cp in result.collab.checkpoints.values() if cp.kind == CheckpointKind.REVERT
        )
        assert revert.mutation.set_params == {node.id: {"path": "a.csv"}}
        restored_path = next(
            p.value for p in result.graph.nodes[node.id].params if p.name == "path"
        )
        assert restored_path == "a.csv"

    def test_revert_remove_nodes_edit_succeeds_and_leaves_session_consistent(self) -> None:
        """Reverting a remove_nodes forward edit must not raise and must not mutate
        session state halfway. The inverse must be computed against the pre-edit graph
        (which still contains the removed node) BEFORE any state change, so a failure
        could never leave the graph reverted without a checkpoint/event.
        """
        store = SessionStore()
        session = store.create()
        n1 = _load_csv_node()
        store.apply_direct_mutation(session.id, GraphMutation(base_version=0, add_nodes=[n1]))
        n2 = _load_csv_node()
        store.apply_direct_mutation(session.id, GraphMutation(base_version=1, add_nodes=[n2]))
        deln = GraphMutation(
            base_version=2, remove_nodes=[n1.id], author="agent", description="del"
        )
        _, edit_cp = store.apply_direct_mutation(session.id, deln)
        assert n1.id not in store.get(session.id).graph.nodes

        result = store.revert_checkpoint(session.id, edit_cp.id)
        assert n1.id in result.graph.nodes
        revert = next(
            cp for cp in result.collab.checkpoints.values() if cp.kind == CheckpointKind.REVERT
        )
        assert revert.previous_graph is not None
        assert edit_cp.id in result.collab.checkpoints
        assert edit_cp.id != revert.id


class TestAcceptProposalCheckpoint:
    def test_accept_proposal_records_an_edit_checkpoint(self) -> None:
        """Regression test: a mutation applied by ACCEPTING a proposal must create an EDIT
        checkpoint (and be revertible), exactly like apply_direct_mutation. Previously
        accept_proposal applied the mutation and bumped the version but recorded no
        checkpoint, so human-accepted edits silently vanished from the revert ledger."""
        store = SessionStore()
        session = store.create()
        node = _load_csv_node()
        apply = GraphMutation(base_version=0, add_nodes=[node], description="add csv")

        proposal = store.add_proposal(session.id, apply)
        session = store.accept_proposal(session.id, proposal.id)

        assert session.version == 1
        edit_cps = [
            cp for cp in session.collab.checkpoints.values() if cp.kind == CheckpointKind.EDIT
        ]
        assert len(edit_cps) == 1
        cp = edit_cps[0]
        assert cp.description == "add csv"
        assert cp.base_version == 0
        assert cp.resulting_version == 1
        assert node.id not in cp.previous_graph.nodes
        assert node.id in session.graph.nodes
        # the accepted edit must be revertible
        reverted = store.revert_checkpoint(session.id, cp.id)
        assert node.id not in reverted.graph.nodes
