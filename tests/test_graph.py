"""Tests for emergentflow.ir.graph — Graph model and structural validators.

Coverage:
  - Valid graph construction + JSON round-trip.
  - Nested subgraph round-trip (a node with subgraph=Graph(...)).
  - schema_version default present in JSON dump.
  - Negative tests for every rejection in the acceptance criteria:
      * Node stored under a key != its id.
      * Edge whose source.node_id is not in nodes.
      * Edge whose target.port_id is not a port on the target node.
      * Edge whose source endpoint points at an IN port (wrong direction).
      * Node whose group_id references a non-existent node.
"""

import json

import pytest
from pydantic import ValidationError

# Importing emergentflow.ir triggers model_rebuild() via graph.py — this is the
# canonical import path that guarantees Node.subgraph is fully resolved.
from emergentflow.ir import (
    CURRENT_SCHEMA_VERSION,
    Direction,
    Edge,
    Graph,
    Node,
    Paradigm,
    Port,
    PortRef,
)

# ---------------------------------------------------------------------------
# Helpers — build canonical two-node, one-edge functional graph
# ---------------------------------------------------------------------------


def _make_source_node() -> Node:
    """A source node with one OUT port."""
    out_port = Port(name="output", direction=Direction.OUT)
    return Node(type="data.load_csv", ports=[out_port])


def _make_target_node() -> Node:
    """A target node with one IN port."""
    in_port = Port(name="input", direction=Direction.IN)
    return Node(type="transform.filter", ports=[in_port])


def _make_simple_graph() -> tuple[Graph, Node, Node, Edge]:
    """Construct a minimal valid two-node, one-edge graph.

    Returns (graph, source_node, target_node, edge).
    """
    src = _make_source_node()
    tgt = _make_target_node()

    out_port_id = src.ports[0].id
    in_port_id = tgt.ports[0].id

    edge = Edge(
        source=PortRef(node_id=src.id, port_id=out_port_id),
        target=PortRef(node_id=tgt.id, port_id=in_port_id),
    )

    graph = Graph(
        nodes={src.id: src, tgt.id: tgt},
        edges={edge.id: edge},
    )
    return graph, src, tgt, edge


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------


class TestGraphConstruction:
    def test_empty_graph_constructs(self):
        g = Graph()
        assert g.nodes == {}
        assert g.edges == {}
        assert g.schema_version == CURRENT_SCHEMA_VERSION
        assert g.paradigm == Paradigm.FUNCTIONAL

    def test_simple_graph_constructs(self):
        graph, src, tgt, edge = _make_simple_graph()
        assert src.id in graph.nodes
        assert tgt.id in graph.nodes
        assert edge.id in graph.edges

    def test_schema_version_default_is_1(self):
        g = Graph()
        assert g.schema_version == 1

    def test_schema_version_in_json_dump(self):
        g = Graph()
        data = json.loads(g.model_dump_json())
        assert "schema_version" in data
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_name_field_optional(self):
        g = Graph(name="My Pipeline")
        assert g.name == "My Pipeline"
        g2 = Graph()
        assert g2.name is None


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


class TestGraphRoundTrip:
    def test_simple_graph_json_round_trip(self):
        graph, src, tgt, edge = _make_simple_graph()
        json_str = graph.model_dump_json()
        restored = Graph.model_validate_json(json_str)

        assert restored.schema_version == graph.schema_version
        assert restored.paradigm == graph.paradigm
        assert set(restored.nodes.keys()) == set(graph.nodes.keys())
        assert set(restored.edges.keys()) == set(graph.edges.keys())

        # Nodes and edges should be equal after round-trip.
        assert restored.nodes[src.id].type == src.type
        assert restored.nodes[tgt.id].type == tgt.type
        restored_edge = restored.edges[edge.id]
        assert restored_edge.source.node_id == edge.source.node_id
        assert restored_edge.target.node_id == edge.target.node_id

    def test_nested_subgraph_round_trip(self):
        """A node with subgraph=Graph(...) should round-trip correctly (Option A nesting)."""
        # Build the inner subgraph.
        inner_src = _make_source_node()
        inner_tgt = _make_target_node()
        inner_out_port_id = inner_src.ports[0].id
        inner_in_port_id = inner_tgt.ports[0].id
        inner_edge = Edge(
            source=PortRef(node_id=inner_src.id, port_id=inner_out_port_id),
            target=PortRef(node_id=inner_tgt.id, port_id=inner_in_port_id),
        )
        inner_graph = Graph(
            name="inner",
            nodes={inner_src.id: inner_src, inner_tgt.id: inner_tgt},
            edges={inner_edge.id: inner_edge},
        )

        # Build the outer graph with one composite node that has a subgraph.
        composite_out_port = Port(name="output", direction=Direction.OUT)
        composite_in_port = Port(name="input", direction=Direction.IN)
        composite_node = Node(
            type="composite.module",
            ports=[composite_out_port, composite_in_port],
            subgraph=inner_graph,
        )

        outer_src = _make_source_node()
        outer_tgt = _make_target_node()
        outer_edge_in = Edge(
            source=PortRef(node_id=outer_src.id, port_id=outer_src.ports[0].id),
            target=PortRef(node_id=composite_node.id, port_id=composite_in_port.id),
        )
        outer_edge_out = Edge(
            source=PortRef(node_id=composite_node.id, port_id=composite_out_port.id),
            target=PortRef(node_id=outer_tgt.id, port_id=outer_tgt.ports[0].id),
        )

        outer_graph = Graph(
            nodes={
                outer_src.id: outer_src,
                composite_node.id: composite_node,
                outer_tgt.id: outer_tgt,
            },
            edges={
                outer_edge_in.id: outer_edge_in,
                outer_edge_out.id: outer_edge_out,
            },
        )

        # Round-trip.
        json_str = outer_graph.model_dump_json()
        restored = Graph.model_validate_json(json_str)

        restored_composite = restored.nodes[composite_node.id]
        assert restored_composite.subgraph is not None
        assert isinstance(restored_composite.subgraph, Graph)
        assert restored_composite.subgraph.name == "inner"
        assert set(restored_composite.subgraph.nodes.keys()) == {
            inner_src.id,
            inner_tgt.id,
        }


# ---------------------------------------------------------------------------
# Negative tests — structural validation rejections
# ---------------------------------------------------------------------------


class TestGraphStructuralRejections:
    def test_node_stored_under_wrong_key_raises(self):
        """A node stored under a key that != node.id must be rejected."""
        node = _make_source_node()
        wrong_key = "definitely-not-the-real-id"
        with pytest.raises((ValidationError, ValueError)):
            Graph(nodes={wrong_key: node})

    def test_edge_stored_under_wrong_key_raises(self):
        """An edge stored under a key that != edge.id must be rejected."""
        src = _make_source_node()
        tgt = _make_target_node()
        edge = Edge(
            source=PortRef(node_id=src.id, port_id=src.ports[0].id),
            target=PortRef(node_id=tgt.id, port_id=tgt.ports[0].id),
        )
        wrong_key = "definitely-not-the-real-edge-id"
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={src.id: src, tgt.id: tgt},
                edges={wrong_key: edge},
            )

    def test_edge_with_dangling_source_node_raises(self):
        """An edge whose source.node_id is not in nodes must be rejected."""
        src = _make_source_node()
        tgt = _make_target_node()
        # Build edge referencing a non-existent source node id.
        edge = Edge(
            source=PortRef(node_id="ghost-node-id", port_id=src.ports[0].id),
            target=PortRef(node_id=tgt.id, port_id=tgt.ports[0].id),
        )
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={tgt.id: tgt},
                edges={edge.id: edge},
            )

    def test_edge_with_dangling_target_node_raises(self):
        """An edge whose target.node_id is not in nodes must be rejected."""
        src = _make_source_node()
        tgt = _make_target_node()
        edge = Edge(
            source=PortRef(node_id=src.id, port_id=src.ports[0].id),
            target=PortRef(node_id="ghost-target-id", port_id=tgt.ports[0].id),
        )
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={src.id: src},
                edges={edge.id: edge},
            )

    def test_edge_with_missing_target_port_raises(self):
        """An edge whose target.port_id is not a port on the target node must be rejected."""
        src = _make_source_node()
        tgt = _make_target_node()
        edge = Edge(
            source=PortRef(node_id=src.id, port_id=src.ports[0].id),
            target=PortRef(node_id=tgt.id, port_id="non-existent-port-id"),
        )
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={src.id: src, tgt.id: tgt},
                edges={edge.id: edge},
            )

    def test_edge_with_missing_source_port_raises(self):
        """An edge whose source.port_id is not a port on the source node must be rejected."""
        src = _make_source_node()
        tgt = _make_target_node()
        edge = Edge(
            source=PortRef(node_id=src.id, port_id="non-existent-source-port"),
            target=PortRef(node_id=tgt.id, port_id=tgt.ports[0].id),
        )
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={src.id: src, tgt.id: tgt},
                edges={edge.id: edge},
            )

    def test_edge_source_pointing_at_in_port_raises(self):
        """An edge whose source references an IN port (wrong direction) must be rejected."""
        # Give the source node an IN port and try to use it as a source.
        in_port = Port(name="input", direction=Direction.IN)
        src_with_in = Node(type="source.bad", ports=[in_port])
        tgt = _make_target_node()
        edge = Edge(
            source=PortRef(node_id=src_with_in.id, port_id=in_port.id),
            target=PortRef(node_id=tgt.id, port_id=tgt.ports[0].id),
        )
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={src_with_in.id: src_with_in, tgt.id: tgt},
                edges={edge.id: edge},
            )

    def test_edge_target_pointing_at_out_port_raises(self):
        """An edge whose target references an OUT port (wrong direction) must be rejected."""
        src = _make_source_node()
        out_port = Port(name="output", direction=Direction.OUT)
        tgt_with_out = Node(type="target.bad", ports=[out_port])
        edge = Edge(
            source=PortRef(node_id=src.id, port_id=src.ports[0].id),
            target=PortRef(node_id=tgt_with_out.id, port_id=out_port.id),
        )
        with pytest.raises((ValidationError, ValueError)):
            Graph(
                nodes={src.id: src, tgt_with_out.id: tgt_with_out},
                edges={edge.id: edge},
            )

    def test_node_with_dangling_group_id_raises(self):
        """A node whose group_id references a non-existent node must be rejected."""
        src = _make_source_node()
        # Assign a group_id that points to nothing in the graph.
        src_with_group = src.model_copy(update={"group_id": "ghost-group-id"})
        with pytest.raises((ValidationError, ValueError)):
            Graph(nodes={src_with_group.id: src_with_group})


# ---------------------------------------------------------------------------
# Convenience method smoke tests
# ---------------------------------------------------------------------------


class TestGraphMutators:
    def test_add_node_inserts_by_id(self):
        g = Graph()
        node = _make_source_node()
        g.add_node(node)
        assert node.id in g.nodes
        assert g.nodes[node.id] is node

    def test_add_edge_inserts_by_id(self):
        src = _make_source_node()
        tgt = _make_target_node()
        edge = Edge(
            source=PortRef(node_id=src.id, port_id=src.ports[0].id),
            target=PortRef(node_id=tgt.id, port_id=tgt.ports[0].id),
        )
        g = Graph(nodes={src.id: src, tgt.id: tgt})
        g.add_edge(edge)
        assert edge.id in g.edges
        assert g.edges[edge.id] is edge
