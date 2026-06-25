"""Tests for emergentflow.ir.node — Node and Position models.

NOTE: Graph does not exist yet (Task 07).  All tests here construct nodes
WITHOUT a subgraph.  Full round-trip including subgraph is tested in Task 07.
"""

import json

import pytest
from pydantic import ValidationError

from emergentflow.ir.common import Direction, Paradigm
from emergentflow.ir.node import Node, Position
from emergentflow.ir.params import Param
from emergentflow.ir.port import Port

# ---------------------------------------------------------------------------
# Position model
# ---------------------------------------------------------------------------


class TestPosition:
    def test_position_defaults_to_origin(self):
        """Position defaults to (0.0, 0.0)."""
        pos = Position()
        assert pos.x == 0.0
        assert pos.y == 0.0

    def test_position_explicit_values(self):
        pos = Position(x=3.5, y=-7.2)
        assert pos.x == 3.5
        assert pos.y == -7.2

    def test_position_unknown_field_raises(self):
        with pytest.raises(ValidationError):
            Position(x=1.0, z=2.0)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Basic construction — valid leaf nodes
# ---------------------------------------------------------------------------


class TestNodeConstruction:
    def test_minimal_node(self):
        """Node with only 'type' set uses all defaults."""
        node = Node(type="data.load_csv")
        assert node.type == "data.load_csv"
        assert node.label is None
        assert node.paradigm == Paradigm.FUNCTIONAL
        assert node.params == []
        assert node.ports == []
        assert node.position.x == 0.0
        assert node.position.y == 0.0
        assert node.group_id is None
        assert node.subgraph is None

    def test_node_with_ports_and_params(self):
        """A full leaf node with ports and params constructs successfully."""
        port_out = Port(name="out", direction=Direction.OUT)
        param = Param(name="path", type_token="str", value="x.csv")

        node = Node(
            type="data.load_csv",
            paradigm=Paradigm.FUNCTIONAL,
            ports=[port_out],
            params=[param],
        )

        assert node.type == "data.load_csv"
        assert node.paradigm == Paradigm.FUNCTIONAL
        assert len(node.ports) == 1
        assert node.ports[0].name == "out"
        assert len(node.params) == 1
        assert node.params[0].name == "path"
        assert node.params[0].value == "x.csv"

    def test_node_with_label(self):
        node = Node(type="ops.relu", label="ReLU Activation")
        assert node.label == "ReLU Activation"

    def test_node_with_declarative_paradigm(self):
        node = Node(type="nn.linear", paradigm=Paradigm.DECLARATIVE)
        assert node.paradigm == Paradigm.DECLARATIVE

    def test_node_with_group_id(self):
        node = Node(type="agent.llm_call", group_id="some-group-id")
        assert node.group_id == "some-group-id"

    def test_node_with_explicit_position(self):
        node = Node(type="vis.scatter", position=Position(x=100.0, y=200.0))
        assert node.position.x == 100.0
        assert node.position.y == 200.0

    def test_node_with_multiple_ports(self):
        ports = [
            Port(name="in1", direction=Direction.IN),
            Port(name="in2", direction=Direction.IN),
            Port(name="out", direction=Direction.OUT),
        ]
        node = Node(type="ops.add", ports=ports)
        assert len(node.ports) == 3


# ---------------------------------------------------------------------------
# ID auto-population & uniqueness
# ---------------------------------------------------------------------------


class TestNodeId:
    def test_id_is_auto_populated(self):
        node = Node(type="data.load_csv")
        assert isinstance(node.id, str)
        assert node.id != ""

    def test_id_is_unique_across_instances(self):
        node1 = Node(type="data.load_csv")
        node2 = Node(type="data.load_csv")
        assert node1.id != node2.id

    def test_many_nodes_have_unique_ids(self):
        nodes = [Node(type=f"op.type_{i}") for i in range(100)]
        ids = [n.id for n in nodes]
        assert len(set(ids)) == 100, "All 100 nodes must have distinct IDs"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestNodeDefaults:
    def test_paradigm_defaults_to_functional(self):
        node = Node(type="data.load_csv")
        assert node.paradigm == Paradigm.FUNCTIONAL

    def test_position_defaults_to_origin(self):
        node = Node(type="data.load_csv")
        assert node.position.x == 0.0
        assert node.position.y == 0.0

    def test_group_id_defaults_to_none(self):
        node = Node(type="data.load_csv")
        assert node.group_id is None

    def test_subgraph_defaults_to_none(self):
        node = Node(type="data.load_csv")
        assert node.subgraph is None

    def test_params_defaults_to_empty_list(self):
        node = Node(type="data.load_csv")
        assert node.params == []

    def test_ports_defaults_to_empty_list(self):
        node = Node(type="data.load_csv")
        assert node.ports == []

    def test_label_defaults_to_none(self):
        node = Node(type="data.load_csv")
        assert node.label is None


# ---------------------------------------------------------------------------
# JSON round-trip (subgraph-less nodes only)
# ---------------------------------------------------------------------------


class TestNodeJsonSerialization:
    def test_minimal_node_round_trip(self):
        """Minimal node serializes and deserializes correctly."""
        original = Node(type="data.load_csv")
        json_str = original.model_dump_json()
        restored = Node.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.label == original.label
        assert restored.paradigm == original.paradigm
        assert restored.params == original.params
        assert restored.ports == original.ports
        assert restored.position.x == original.position.x
        assert restored.position.y == original.position.y
        assert restored.group_id == original.group_id
        assert restored.subgraph is None

    def test_node_with_ports_and_params_round_trip(self):
        """Node with ports and params round-trips through JSON."""
        port = Port(name="out", direction=Direction.OUT)
        param = Param(name="path", type_token="str", value="x.csv")
        original = Node(
            type="data.load_csv",
            paradigm=Paradigm.FUNCTIONAL,
            ports=[port],
            params=[param],
            position=Position(x=42.0, y=99.5),
        )

        json_str = original.model_dump_json()
        restored = Node.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.paradigm == original.paradigm
        assert len(restored.ports) == 1
        assert restored.ports[0].name == "out"
        assert len(restored.params) == 1
        assert restored.params[0].name == "path"
        assert restored.params[0].value == "x.csv"
        assert restored.position.x == 42.0
        assert restored.position.y == 99.5

    def test_paradigm_serializes_as_plain_string(self):
        """Paradigm enum serializes as plain string in JSON."""
        node = Node(type="data.load_csv", paradigm=Paradigm.FUNCTIONAL)
        d = json.loads(node.model_dump_json())
        assert d["paradigm"] == "functional"
        assert isinstance(d["paradigm"], str)

    def test_subgraph_null_in_json(self):
        """subgraph serializes as null when None."""
        node = Node(type="data.load_csv")
        d = json.loads(node.model_dump_json())
        assert d["subgraph"] is None


# ---------------------------------------------------------------------------
# Validation — type field
# ---------------------------------------------------------------------------


class TestNodeValidation:
    def test_empty_type_raises(self):
        """Empty type string is rejected."""
        with pytest.raises(ValidationError):
            Node(type="")

    def test_whitespace_only_type_raises(self):
        """Whitespace-only type string is rejected."""
        with pytest.raises(ValidationError):
            Node(type="   ")

    def test_unknown_field_raises(self):
        """Unknown kwargs are rejected (extra=forbid from IRModel)."""
        with pytest.raises(ValidationError):
            Node(type="data.load_csv", unknown="nope")  # type: ignore[call-arg]

    def test_none_type_raises(self):
        """Missing type is rejected."""
        with pytest.raises(ValidationError):
            Node(type=None)  # type: ignore[arg-type]
