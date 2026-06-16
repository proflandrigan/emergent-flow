"""Tests for colonymind.ir.port — Port model."""

import json

import pytest
from pydantic import ValidationError

from colonymind.ir.common import Cardinality, Direction, IRId, new_id
from colonymind.ir.port import Port


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


class TestPortConstruction:
    def test_valid_in_port_with_defaults(self):
        """IN port with minimal args uses defaults for data_type and cardinality."""
        port = Port(name="input", direction=Direction.IN)
        assert port.name == "input"
        assert port.direction == Direction.IN
        assert port.data_type == "any"
        assert port.cardinality == Cardinality.ONE

    def test_valid_out_port_with_defaults(self):
        """OUT port with minimal args uses defaults for data_type and cardinality."""
        port = Port(name="output", direction=Direction.OUT)
        assert port.name == "output"
        assert port.direction == Direction.OUT
        assert port.data_type == "any"
        assert port.cardinality == Cardinality.ONE

    def test_explicit_data_type(self):
        """Can set explicit data_type."""
        port = Port(
            name="typed_port",
            direction=Direction.IN,
            data_type="float32",
        )
        assert port.data_type == "float32"

    def test_explicit_cardinality_many(self):
        """Can set cardinality to MANY."""
        port = Port(
            name="multi_input",
            direction=Direction.IN,
            cardinality=Cardinality.MANY,
        )
        assert port.cardinality == Cardinality.MANY

    def test_all_fields_explicit(self):
        """All fields can be set explicitly."""
        port = Port(
            name="full_port",
            direction=Direction.OUT,
            data_type="tensor",
            cardinality=Cardinality.MANY,
        )
        assert port.name == "full_port"
        assert port.direction == Direction.OUT
        assert port.data_type == "tensor"
        assert port.cardinality == Cardinality.MANY


# ---------------------------------------------------------------------------
# ID generation & uniqueness
# ---------------------------------------------------------------------------


class TestPortId:
    def test_id_is_auto_populated(self):
        """Port.id is auto-populated via Field(default_factory=new_id)."""
        port = Port(name="test", direction=Direction.IN)
        assert isinstance(port.id, str)
        assert port.id != ""

    def test_id_is_unique_across_instances(self):
        """Each Port instance gets a distinct id."""
        port1 = Port(name="p1", direction=Direction.IN)
        port2 = Port(name="p2", direction=Direction.IN)
        assert port1.id != port2.id

    def test_id_is_irid_string(self):
        """id is an IRId (str)."""
        port = Port(name="test", direction=Direction.IN)
        assert isinstance(port.id, str)
        # IRId is just a str alias, so any string is valid.

    def test_many_ports_have_unique_ids(self):
        """Generate many ports and verify all IDs are distinct."""
        ports = [Port(name=f"p{i}", direction=Direction.IN) for i in range(100)]
        ids = [p.id for p in ports]
        assert len(set(ids)) == 100, "All 100 ports must have distinct IDs"


# ---------------------------------------------------------------------------
# Field defaults
# ---------------------------------------------------------------------------


class TestPortDefaults:
    def test_data_type_default_is_any(self):
        port = Port(name="test", direction=Direction.IN)
        assert port.data_type == "any"

    def test_cardinality_default_is_one(self):
        port = Port(name="test", direction=Direction.IN)
        assert port.cardinality == Cardinality.ONE


# ---------------------------------------------------------------------------
# JSON serialization & round-trip
# ---------------------------------------------------------------------------


class TestPortJsonSerialization:
    def test_model_dump_json_round_trip(self):
        """Port serialized to JSON and back is equal."""
        original = Port(
            name="test_port",
            direction=Direction.OUT,
            data_type="int32",
            cardinality=Cardinality.MANY,
        )
        json_str = original.model_dump_json()
        restored = Port.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.direction == original.direction
        assert restored.data_type == original.data_type
        assert restored.cardinality == original.cardinality

    def test_enums_serialize_as_plain_strings(self):
        """Direction and Cardinality serialize as plain strings in JSON."""
        port = Port(
            name="enum_test",
            direction=Direction.IN,
            cardinality=Cardinality.MANY,
        )
        d = json.loads(port.model_dump_json())

        assert d["direction"] == "in"
        assert d["cardinality"] == "many"
        assert isinstance(d["direction"], str)
        assert isinstance(d["cardinality"], str)

    def test_model_dump_plain_strings(self):
        """model_dump() also returns enums as plain strings."""
        port = Port(name="test", direction=Direction.OUT, cardinality=Cardinality.ONE)
        d = port.model_dump()

        assert d["direction"] == "out"
        assert d["cardinality"] == "one"


# ---------------------------------------------------------------------------
# Validation — empty/whitespace name
# ---------------------------------------------------------------------------


class TestPortValidation:
    def test_empty_name_raises(self):
        """Empty name is rejected."""
        with pytest.raises(ValidationError):
            Port(name="", direction=Direction.IN)

    def test_whitespace_only_name_raises(self):
        """Whitespace-only name is rejected."""
        with pytest.raises(ValidationError):
            Port(name="   ", direction=Direction.OUT)

    def test_unknown_field_raises(self):
        """Unknown kwargs are rejected (extra=forbid from IRModel)."""
        with pytest.raises(ValidationError):
            Port(name="test", direction=Direction.IN, unknown_field="nope")  # type: ignore[call-arg]

    def test_none_name_raises(self):
        """None name is rejected."""
        with pytest.raises(ValidationError):
            Port(name=None, direction=Direction.IN)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Enum usage
# ---------------------------------------------------------------------------


class TestPortEnumUsage:
    def test_direction_in_port(self):
        port = Port(name="in_port", direction=Direction.IN)
        assert port.direction == Direction.IN
        assert port.direction == "in"

    def test_direction_out_port(self):
        port = Port(name="out_port", direction=Direction.OUT)
        assert port.direction == Direction.OUT
        assert port.direction == "out"

    def test_cardinality_one_port(self):
        port = Port(name="single", direction=Direction.IN, cardinality=Cardinality.ONE)
        assert port.cardinality == Cardinality.ONE
        assert port.cardinality == "one"

    def test_cardinality_many_port(self):
        port = Port(
            name="multi", direction=Direction.OUT, cardinality=Cardinality.MANY
        )
        assert port.cardinality == Cardinality.MANY
        assert port.cardinality == "many"
