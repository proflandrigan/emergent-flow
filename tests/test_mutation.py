"""
tests/test_mutation.py
~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 2 — the mutation protocol: GraphMutation, apply_mutation,
propose_diagnostics (emergentflow/ir/mutation.py).

Covers: apply order (removes -> adds -> param sets), every MutationError case,
purity (input graph/mutation never mutated), determinism, a JSON round-trip
through a real NodeDefinition.instantiate(...) node (agents send JSON), and
propose_diagnostics folding both MutationError and ef.validate's Diagnostics
into one shape.
"""

from __future__ import annotations

import pytest

from emergentflow.codegen.validation import Severity
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import (
    GraphMutation,
    MutationError,
    apply_mutation,
    invert_mutation,
    propose_diagnostics,
)
from emergentflow.ir.node import Node, Position
from emergentflow.ir.params import Param
from emergentflow.nodes.examples.cast_types import CastTypes
from emergentflow.nodes.examples.load_csv import LoadCsv


def _load_csv_node(path: str = "a.csv") -> Node:
    return LoadCsv().instantiate(path=path)


def _one_node_graph() -> Graph:
    node = _load_csv_node()
    return Graph(nodes={node.id: node})


def _wired_pair() -> tuple[Node, Node, Edge]:
    """A data.load_csv -> clean.cast_types pair, connected by one edge."""
    source = _load_csv_node()
    target = CastTypes().instantiate(dtypes={})
    out_port = next(p for p in source.ports if p.direction == Direction.OUT)
    in_port = next(p for p in target.ports if p.direction == Direction.IN)
    edge = Edge(
        source=PortRef(node_id=source.id, port_id=out_port.id),
        target=PortRef(node_id=target.id, port_id=in_port.id),
    )
    return source, target, edge


# ---------------------------------------------------------------------------
# Adds
# ---------------------------------------------------------------------------


class TestApplyMutationAdds:
    def test_add_node_appends(self) -> None:
        graph = Graph()
        node = _load_csv_node()
        m = GraphMutation(base_version=1, add_nodes=[node])
        result = apply_mutation(graph, m)
        assert node.id in result.nodes
        assert len(result.nodes) == 1

    def test_add_edge(self) -> None:
        source, target, edge = _wired_pair()
        graph = Graph(nodes={source.id: source, target.id: target})
        m = GraphMutation(base_version=1, add_edges=[edge])
        result = apply_mutation(graph, m)
        assert edge.id in result.edges

    def test_add_node_colliding_with_existing_id_raises(self) -> None:
        graph = _one_node_graph()
        existing_id = next(iter(graph.nodes))
        dup = Node(id=existing_id, type="data.load_csv", label="dup")
        m = GraphMutation(base_version=1, add_nodes=[dup])
        with pytest.raises(MutationError):
            apply_mutation(graph, m)

    def test_add_duplicate_node_ids_within_mutation_raises(self) -> None:
        graph = Graph()
        a = Node(id="dup-id", type="data.load_csv", label="a")
        b = Node(id="dup-id", type="data.load_csv", label="b")
        m = GraphMutation(base_version=1, add_nodes=[a, b])
        with pytest.raises(MutationError):
            apply_mutation(graph, m)

    def test_add_node_at_default_position_gets_cascaded(self) -> None:
        graph = Graph()
        node = _load_csv_node()
        m = GraphMutation(base_version=1, add_nodes=[node])
        result = apply_mutation(graph, m)
        assert result.nodes[node.id].position != Position(x=0.0, y=0.0)

    def test_add_multiple_nodes_at_default_position_do_not_collide(self) -> None:
        graph = Graph()
        node_a = _load_csv_node()
        node_b = _load_csv_node()
        m = GraphMutation(base_version=1, add_nodes=[node_a, node_b])
        result = apply_mutation(graph, m)
        assert result.nodes[node_a.id].position != result.nodes[node_b.id].position

    def test_add_node_with_explicit_position_is_preserved(self) -> None:
        graph = Graph()
        node = _load_csv_node().model_copy(update={"position": Position(x=5.0, y=5.0)})
        m = GraphMutation(base_version=1, add_nodes=[node])
        result = apply_mutation(graph, m)
        assert result.nodes[node.id].position == Position(x=5.0, y=5.0)

    def test_cascaded_default_position_does_not_collide_with_explicit_sibling(self) -> None:
        """A default-positioned add must not land on a position an explicitly-positioned
        add in the *same* mutation already claims (regression: the cascade used to only
        check against the pre-existing graph, not other nodes in this batch)."""
        graph = Graph()
        explicit_node = _load_csv_node().model_copy(update={"position": Position(x=60.0, y=60.0)})
        default_node = _load_csv_node()
        m = GraphMutation(base_version=1, add_nodes=[explicit_node, default_node])
        result = apply_mutation(graph, m)
        assert result.nodes[explicit_node.id].position != result.nodes[default_node.id].position

    def test_add_edge_colliding_with_existing_id_raises(self) -> None:
        source, target, edge = _wired_pair()
        edge = edge.model_copy(update={"id": "dup-edge"})
        graph = Graph(
            nodes={source.id: source, target.id: target},
            edges={edge.id: edge},
        )
        dup_edge = edge.model_copy()
        m = GraphMutation(base_version=1, add_edges=[dup_edge])
        with pytest.raises(MutationError):
            apply_mutation(graph, m)


# ---------------------------------------------------------------------------
# Removes
# ---------------------------------------------------------------------------


class TestApplyMutationRemoves:
    def test_remove_node(self) -> None:
        graph = _one_node_graph()
        node_id = next(iter(graph.nodes))
        m = GraphMutation(base_version=1, remove_nodes=[node_id])
        result = apply_mutation(graph, m)
        assert node_id not in result.nodes
        assert len(result.nodes) == 0

    def test_remove_missing_node_raises(self) -> None:
        graph = Graph()
        m = GraphMutation(base_version=1, remove_nodes=["does-not-exist"])
        with pytest.raises(MutationError):
            apply_mutation(graph, m)

    def test_remove_edge(self) -> None:
        source, target, edge = _wired_pair()
        graph = Graph(
            nodes={source.id: source, target.id: target},
            edges={edge.id: edge},
        )
        m = GraphMutation(base_version=1, remove_edges=[edge.id])
        result = apply_mutation(graph, m)
        assert edge.id not in result.edges

    def test_remove_missing_edge_raises(self) -> None:
        graph = Graph()
        m = GraphMutation(base_version=1, remove_edges=["does-not-exist"])
        with pytest.raises(MutationError):
            apply_mutation(graph, m)

    def test_remove_node_leaving_dangling_edge_raises(self) -> None:
        source, target, edge = _wired_pair()
        graph = Graph(
            nodes={source.id: source, target.id: target},
            edges={edge.id: edge},
        )
        # Removing the source node without removing the edge that references it
        # must surface as a MutationError (Graph's structural validator rejects
        # the dangling edge; apply_mutation folds that into MutationError).
        m = GraphMutation(base_version=1, remove_nodes=[source.id])
        with pytest.raises(MutationError):
            apply_mutation(graph, m)


# ---------------------------------------------------------------------------
# set_params
# ---------------------------------------------------------------------------


class TestApplyMutationSetParams:
    def test_set_params_updates_value(self) -> None:
        graph = _one_node_graph()
        node_id = next(iter(graph.nodes))
        m = GraphMutation(base_version=1, set_params={node_id: {"path": "b.csv"}})
        result = apply_mutation(graph, m)
        updated = result.nodes[node_id]
        path_param = next(p for p in updated.params if p.name == "path")
        assert path_param.value == "b.csv"

    def test_set_params_unknown_node_raises(self) -> None:
        graph = Graph()
        m = GraphMutation(base_version=1, set_params={"does-not-exist": {"path": "b.csv"}})
        with pytest.raises(MutationError):
            apply_mutation(graph, m)

    def test_set_params_rejected_by_node_contract_raises(self) -> None:
        # "path" is a real param on data.load_csv; "not_a_real_param" is not
        # declared by the definition, so validate_node must reject it.
        graph = _one_node_graph()
        node_id = next(iter(graph.nodes))
        m = GraphMutation(base_version=1, set_params={node_id: {"not_a_real_param": "x"}})
        with pytest.raises(MutationError):
            apply_mutation(graph, m)

    def test_set_params_on_unregistered_type_is_best_effort(self) -> None:
        node = Node(id="n1", type="totally.unregistered.type", label="x")
        graph = Graph(nodes={node.id: node})
        m = GraphMutation(base_version=1, set_params={"n1": {"whatever": "value"}})
        result = apply_mutation(graph, m)
        updated_param = next(p for p in result.nodes["n1"].params if p.name == "whatever")
        assert updated_param.value == "value"

    def test_set_params_applies_to_node_added_in_same_mutation(self) -> None:
        # Proves apply order is removes -> adds -> param sets: a param set
        # targeting a node added by the SAME mutation must see that node.
        graph = Graph()
        node = _load_csv_node()
        m = GraphMutation(
            base_version=1,
            add_nodes=[node],
            set_params={node.id: {"path": "overridden.csv"}},
        )
        result = apply_mutation(graph, m)
        path_param = next(p for p in result.nodes[node.id].params if p.name == "path")
        assert path_param.value == "overridden.csv"

    def test_set_params_preserves_ref_and_description_on_refd_param(self) -> None:
        # A param ref'd to a graph-level parameter (issue #116) must keep its `ref`
        # (and `description`) when set_params updates only its value -- rebuilding
        # the Param field-by-field would silently sever the author's graph-param
        # wiring on any agent-proposed value edit.
        node = Node(
            id="n1",
            type="test.sink",
            params=[
                Param(
                    name="value",
                    type_token="int",
                    value=999,
                    default=999,
                    ref="p",
                    description="linked to graph param p",
                ),
            ],
        )
        graph = Graph(nodes={node.id: node})
        m = GraphMutation(base_version=0, set_params={"n1": {"value": 42}})
        result = apply_mutation(graph, m)
        updated = next(p for p in result.nodes["n1"].params if p.name == "value")
        assert updated.value == 42
        assert updated.ref == "p"
        assert updated.description == "linked to graph param p"
        assert updated.type_token == "int"
        assert updated.default == 999

    def test_set_params_does_not_mutate_input_node(self) -> None:
        # Purity: the value update on a ref'd param must not mutate the source node.
        node = Node(
            id="n1",
            type="test.sink",
            params=[Param(name="value", type_token="int", value=999, ref="p")],
        )
        graph = Graph(nodes={node.id: node})
        m = GraphMutation(base_version=0, set_params={"n1": {"value": 42}})
        apply_mutation(graph, m)
        original = graph.nodes["n1"].params[0]
        assert original.value == 999
        assert original.ref == "p"


# ---------------------------------------------------------------------------
# invert_mutation
# ---------------------------------------------------------------------------


class TestInvertMutation:
    def test_invert_set_params_restores_original_value(self) -> None:
        # Forward: set a param; inverse must restore its original value.
        graph = _one_node_graph()
        node_id = next(iter(graph.nodes))
        m = GraphMutation(base_version=1, set_params={node_id: {"path": "b.csv"}})
        forward = apply_mutation(graph, m)
        restored = apply_mutation(forward, invert_mutation(graph, m))
        assert graph.model_dump(mode="json") == restored.model_dump(mode="json")

    def test_invert_add_node(self) -> None:
        graph = _one_node_graph()
        node = _load_csv_node("new.csv")
        m = GraphMutation(base_version=1, add_nodes=[node])
        forward = apply_mutation(graph, m)
        restored = apply_mutation(forward, invert_mutation(graph, m))
        assert graph.model_dump(mode="json") == restored.model_dump(mode="json")

    def test_invert_remove_node(self) -> None:
        node_a = _load_csv_node()
        node_b = _load_csv_node("b.csv")
        node_b = node_b.model_copy(update={"position": Position(x=200.0, y=200.0)})
        graph = Graph(nodes={node_a.id: node_a, node_b.id: node_b})
        m = GraphMutation(base_version=1, remove_nodes=[node_b.id])
        forward = apply_mutation(graph, m)
        restored = apply_mutation(forward, invert_mutation(graph, m))
        assert graph.model_dump(mode="json") == restored.model_dump(mode="json")

    def test_invert_new_param_raises(self) -> None:
        # set_params on a param the ORIGINAL node does not carry is not invertible:
        # the graph-mutation protocol has no way to express removing a param, so a
        # forward-only small-set must not silently produce a broken inverse.
        node = Node(id="n1", type="totally.unregistered.type", label="x")
        graph = Graph(nodes={node.id: node})
        m = GraphMutation(base_version=1, set_params={"n1": {"fresh": 1}})
        apply_mutation(graph, m)  # forward apply works (best-effort for unregistered)
        with pytest.raises(MutationError, match="not invertible"):
            invert_mutation(graph, m)


# ---------------------------------------------------------------------------
# Purity & determinism
# ---------------------------------------------------------------------------


class TestApplyMutationPurity:
    def test_input_graph_not_mutated(self) -> None:
        graph = _one_node_graph()
        before = graph.model_dump(mode="json")
        node = _load_csv_node("new.csv")
        m = GraphMutation(base_version=1, add_nodes=[node])
        apply_mutation(graph, m)
        after = graph.model_dump(mode="json")
        assert before == after

    def test_input_mutation_not_mutated(self) -> None:
        graph = Graph()
        node = _load_csv_node()
        m = GraphMutation(base_version=1, add_nodes=[node])
        before = m.model_dump(mode="json")
        apply_mutation(graph, m)
        after = m.model_dump(mode="json")
        assert before == after

    def test_apply_is_deterministic(self) -> None:
        graph = _one_node_graph()
        node_id = next(iter(graph.nodes))
        m = GraphMutation(base_version=1, set_params={node_id: {"path": "b.csv"}})
        result_a = apply_mutation(graph, m)
        result_b = apply_mutation(graph, m)
        assert result_a.model_dump(mode="json") == result_b.model_dump(mode="json")


class TestApplyMutationPreservesGraphParams:
    def test_graph_level_params_survive_a_mutation(self) -> None:
        # issue #116 graph-level params are a real Graph field; a mutation that
        # adds a node/edge or edits node params must not silently drop them
        # (regression: the reconstructed Graph omitted `params`).
        graph = Graph(
            nodes={node.id: node for node in [_load_csv_node()]},
            params={
                "epochs": Param(name="epochs", type_token="int", value=10, default=1),
            },
        )
        node_id = next(iter(graph.nodes))
        m = GraphMutation(
            base_version=1,
            add_nodes=[CastTypes().instantiate(dtypes={})],
            set_params={node_id: {"path": "b.csv"}},
        )
        result = apply_mutation(graph, m)
        assert result.params == graph.params

    def test_graph_level_params_survive_a_noop_mutation(self) -> None:
        graph = Graph(
            nodes={node.id: node for node in [_load_csv_node()]},
            params={
                "seed": Param(name="seed", type_token="int", value=42, default=0),
            },
        )
        result = apply_mutation(graph, GraphMutation(base_version=1))
        assert result.params == graph.params


# ---------------------------------------------------------------------------
# JSON round-trip (agents send JSON)
# ---------------------------------------------------------------------------


class TestMutationJSONRoundTrip:
    def test_instantiated_node_round_trips_through_json(self) -> None:
        node = LoadCsv().instantiate(path="round-trip.csv")
        m = GraphMutation(base_version=3, add_nodes=[node], author="agent-x")
        raw = m.model_dump_json()
        restored = GraphMutation.model_validate_json(raw)
        assert restored == m

        graph = Graph()
        result_direct = apply_mutation(graph, m)
        result_restored = apply_mutation(graph, restored)
        assert result_direct.model_dump(mode="json") == result_restored.model_dump(mode="json")


# ---------------------------------------------------------------------------
# propose_diagnostics
# ---------------------------------------------------------------------------


class TestProposeDiagnostics:
    def test_valid_mutation_yields_ok_diagnostics(self) -> None:
        graph = Graph()
        node = _load_csv_node()
        m = GraphMutation(base_version=1, add_nodes=[node])
        diagnostics = propose_diagnostics(graph, m)
        assert diagnostics.ok

    def test_mutation_error_folds_into_diagnostics(self) -> None:
        graph = Graph()
        m = GraphMutation(base_version=1, remove_nodes=["does-not-exist"])
        diagnostics = propose_diagnostics(graph, m)
        assert not diagnostics.ok
        assert len(diagnostics.diagnostics) == 1
        assert diagnostics.diagnostics[0].code == "mutation_error"
        assert diagnostics.diagnostics[0].severity == Severity.ERROR

    def test_required_unconnected_input_surfaces_as_error(self) -> None:
        # clean.cast_types declares a REQUIRED IN "frame" port (PortSpec default
        # required=True). Adding it with no inbound edge must surface as an
        # ef.validate error diagnostic, not raise.
        graph = Graph()
        node = CastTypes().instantiate(dtypes={})
        m = GraphMutation(base_version=1, add_nodes=[node])
        diagnostics = propose_diagnostics(graph, m)
        assert not diagnostics.ok
        assert any(d.code == "required_input_unconnected" for d in diagnostics.diagnostics)
