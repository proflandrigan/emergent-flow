"""Tests for colonymind.nodes.spec — the serializable half of the contract.

These mirror the IR round-trip tests (Story 2): a spec must validate its fields
and round-trip losslessly through JSON, since the frontend consumes it with no
Python present.
"""

import pytest
from pydantic import ValidationError

from colonymind.ir.common import Cardinality, Direction, Paradigm
from colonymind.nodes.spec import NodeSpec, ParamSpec, PortSpec, ValidationHints


class TestPortSpec:
    def test_minimal(self):
        ps = PortSpec(name="out", direction=Direction.OUT)
        assert ps.data_type == "any"
        assert ps.cardinality == Cardinality.ONE
        assert ps.required is True

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            PortSpec(name="  ", direction=Direction.IN)

    def test_unknown_field_raises(self):
        with pytest.raises(ValidationError):
            PortSpec(name="x", direction=Direction.IN, bogus=1)  # type: ignore[call-arg]

    def test_round_trip(self):
        ps = PortSpec(
            name="table",
            direction=Direction.IN,
            data_type="Table",
            cardinality=Cardinality.MANY,
            required=False,
            label="In",
            help="h",
        )
        assert PortSpec.model_validate_json(ps.model_dump_json()) == ps


class TestParamSpec:
    def test_minimal(self):
        ps = ParamSpec(name="path", type_token="str")
        assert ps.default is None
        assert ps.required is False
        assert ps.hints is None

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            ParamSpec(name="", type_token="str")

    def test_empty_type_token_raises(self):
        with pytest.raises(ValidationError):
            ParamSpec(name="path", type_token="  ")

    def test_round_trip_with_hints(self):
        ps = ParamSpec(
            name="strategy",
            type_token="str",
            default="mean",
            required=True,
            label="Strategy",
            help="how",
            hints=ValidationHints(choices=["mean", "median"], widget="select"),
        )
        assert ParamSpec.model_validate_json(ps.model_dump_json()) == ps


class TestValidationHints:
    def test_all_optional(self):
        assert ValidationHints().min is None

    def test_round_trip(self):
        h = ValidationHints(
            min=0,
            max=10,
            step=1,
            choices=[1, 2],
            min_length=1,
            max_length=5,
            pattern=r"\d+",
            widget="slider",
        )
        assert ValidationHints.model_validate_json(h.model_dump_json()) == h


class TestNodeSpec:
    def test_minimal(self):
        spec = NodeSpec(type="data.load_csv", family="data", label="Load CSV")
        assert spec.version == 1
        assert spec.paradigm == Paradigm.FUNCTIONAL
        assert spec.ports == []
        assert spec.params == []

    def test_empty_type_raises(self):
        with pytest.raises(ValidationError):
            NodeSpec(type="", family="data", label="x")

    def test_zero_version_raises(self):
        with pytest.raises(ValidationError):
            NodeSpec(type="t", family="data", label="x", version=0)

    def test_round_trip(self):
        spec = NodeSpec(
            type="clean.impute_missing",
            version=2,
            family="clean",
            label="Impute",
            paradigm=Paradigm.FUNCTIONAL,
            ports=[PortSpec(name="table", direction=Direction.OUT, data_type="Table")],
            params=[
                ParamSpec(
                    name="strategy",
                    type_token="str",
                    default="mean",
                    hints=ValidationHints(choices=["mean"]),
                )
            ],
        )
        assert NodeSpec.model_validate_json(spec.model_dump_json()) == spec
