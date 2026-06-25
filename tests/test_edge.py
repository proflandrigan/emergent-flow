"""
tests.test_edge
~~~~~~~~~~~~~~~
Tests for emergentflow.ir.edge module: PortRef and Edge models.

Coverage:
  - Valid edge construction
  - id auto-population and uniqueness
  - type_compatible default (None)
  - JSON round-trip (model_dump_json / model_validate_json)
  - Empty endpoint-id rejection
  - Unknown-kwarg rejection (extra=forbid)
"""

import pytest
from pydantic import ValidationError

from emergentflow.ir.edge import Edge, PortRef


class TestPortRef:
    """Tests for PortRef endpoint reference model."""

    def test_valid_portref(self):
        """Create a valid PortRef with node_id and port_id."""
        port_ref = PortRef(node_id="node-123", port_id="port-456")
        assert port_ref.node_id == "node-123"
        assert port_ref.port_id == "port-456"

    def test_portref_empty_node_id(self):
        """PortRef rejects empty node_id."""
        with pytest.raises(ValidationError) as exc_info:
            PortRef(node_id="", port_id="port-456")
        assert "node_id" in str(exc_info.value)

    def test_portref_whitespace_only_node_id(self):
        """PortRef rejects whitespace-only node_id."""
        with pytest.raises(ValidationError) as exc_info:
            PortRef(node_id="   ", port_id="port-456")
        assert "node_id" in str(exc_info.value)

    def test_portref_empty_port_id(self):
        """PortRef rejects empty port_id."""
        with pytest.raises(ValidationError) as exc_info:
            PortRef(node_id="node-123", port_id="")
        assert "port_id" in str(exc_info.value)

    def test_portref_whitespace_only_port_id(self):
        """PortRef rejects whitespace-only port_id."""
        with pytest.raises(ValidationError) as exc_info:
            PortRef(node_id="node-123", port_id="   ")
        assert "port_id" in str(exc_info.value)

    def test_portref_unknown_kwarg(self):
        """PortRef rejects unknown kwargs (extra=forbid)."""
        with pytest.raises(ValidationError) as exc_info:
            PortRef(node_id="node-123", port_id="port-456", unknown_field="value")
        assert (
            "unknown_field" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()
        )


class TestEdge:
    """Tests for Edge model."""

    def test_valid_edge_construction(self):
        """Construct a valid edge with source and target PortRefs."""
        source = PortRef(node_id="n1", port_id="p1")
        target = PortRef(node_id="n2", port_id="p2")
        edge = Edge(source=source, target=target)

        assert edge.source.node_id == "n1"
        assert edge.source.port_id == "p1"
        assert edge.target.node_id == "n2"
        assert edge.target.port_id == "p2"

    def test_edge_construction_with_inline_portrefs(self):
        """Construct edge with inline PortRef dicts."""
        edge = Edge(
            source={"node_id": "n1", "port_id": "p1"},
            target={"node_id": "n2", "port_id": "p2"},
        )
        assert edge.source.node_id == "n1"
        assert edge.target.node_id == "n2"

    def test_edge_id_auto_population(self):
        """Edge id is auto-populated if not provided."""
        edge = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
        )
        assert edge.id is not None
        assert isinstance(edge.id, str)
        assert len(edge.id) > 0

    def test_edge_id_uniqueness(self):
        """Each edge gets a unique id."""
        edge1 = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
        )
        edge2 = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
        )
        assert edge1.id != edge2.id

    def test_edge_type_compatible_default_none(self):
        """Edge.type_compatible defaults to None."""
        edge = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
        )
        assert edge.type_compatible is None

    def test_edge_type_compatible_explicit_true(self):
        """Edge.type_compatible can be set to True."""
        edge = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
            type_compatible=True,
        )
        assert edge.type_compatible is True

    def test_edge_type_compatible_explicit_false(self):
        """Edge.type_compatible can be set to False."""
        edge = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
            type_compatible=False,
        )
        assert edge.type_compatible is False

    def test_edge_json_round_trip(self):
        """Edge round-trips via model_dump_json and model_validate_json."""
        original = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
            type_compatible=True,
        )
        json_str = original.model_dump_json()
        restored = Edge.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.source.node_id == original.source.node_id
        assert restored.source.port_id == original.source.port_id
        assert restored.target.node_id == original.target.node_id
        assert restored.target.port_id == original.target.port_id
        assert restored.type_compatible == original.type_compatible

    def test_edge_json_round_trip_with_none_type_compatible(self):
        """Edge round-trips with type_compatible=None."""
        original = Edge(
            source=PortRef(node_id="n1", port_id="p1"),
            target=PortRef(node_id="n2", port_id="p2"),
        )
        json_str = original.model_dump_json()
        restored = Edge.model_validate_json(json_str)

        assert restored.type_compatible is None

    def test_edge_unknown_kwarg(self):
        """Edge rejects unknown kwargs (extra=forbid)."""
        with pytest.raises(ValidationError) as exc_info:
            Edge(
                source=PortRef(node_id="n1", port_id="p1"),
                target=PortRef(node_id="n2", port_id="p2"),
                unknown_field="value",
            )
        assert (
            "unknown_field" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()
        )

    def test_edge_missing_source(self):
        """Edge requires source PortRef."""
        with pytest.raises(ValidationError):
            Edge(target=PortRef(node_id="n2", port_id="p2"))

    def test_edge_missing_target(self):
        """Edge requires target PortRef."""
        with pytest.raises(ValidationError):
            Edge(source=PortRef(node_id="n1", port_id="p1"))

    def test_edge_invalid_source_portref(self):
        """Edge rejects invalid source PortRef (empty node_id)."""
        with pytest.raises(ValidationError):
            Edge(
                source=PortRef(node_id="", port_id="p1"),
                target=PortRef(node_id="n2", port_id="p2"),
            )

    def test_edge_invalid_target_portref(self):
        """Edge rejects invalid target PortRef (empty port_id)."""
        with pytest.raises(ValidationError):
            Edge(
                source=PortRef(node_id="n1", port_id="p1"),
                target=PortRef(node_id="n2", port_id=""),
            )
