"""Tests for colonymind.ir.common — core primitives."""

import pytest
from pydantic import ValidationError

from colonymind.ir.common import (
    ArtifactRef,
    Cardinality,
    Direction,
    IRId,
    IRModel,
    Paradigm,
    new_id,
)

# ---------------------------------------------------------------------------
# Enum member values
# ---------------------------------------------------------------------------


class TestDirectionEnum:
    def test_in_value(self):
        assert Direction.IN.value == "in"

    def test_out_value(self):
        assert Direction.OUT.value == "out"

    def test_serializes_as_string(self):
        """Direction members must behave as plain strings (str, Enum)."""
        assert Direction.IN == "in"
        assert Direction.OUT == "out"


class TestCardinalityEnum:
    def test_one_value(self):
        assert Cardinality.ONE.value == "one"

    def test_many_value(self):
        assert Cardinality.MANY.value == "many"

    def test_serializes_as_string(self):
        assert Cardinality.ONE == "one"
        assert Cardinality.MANY == "many"


class TestParadigmEnum:
    def test_functional_value(self):
        assert Paradigm.FUNCTIONAL.value == "functional"

    def test_declarative_value(self):
        assert Paradigm.DECLARATIVE.value == "declarative"

    def test_serializes_as_string(self):
        assert Paradigm.FUNCTIONAL == "functional"
        assert Paradigm.DECLARATIVE == "declarative"


# ---------------------------------------------------------------------------
# Enum serialisation inside a model
# ---------------------------------------------------------------------------


class TestEnumInModel:
    """Enums embedded in an IRModel subclass must dump as plain strings."""

    class _Sample(IRModel):
        direction: Direction
        paradigm: Paradigm
        cardinality: Cardinality

    def test_model_dump_plain_strings(self):
        m = self._Sample(
            direction=Direction.IN,
            paradigm=Paradigm.FUNCTIONAL,
            cardinality=Cardinality.MANY,
        )
        d = m.model_dump()
        assert d["direction"] == "in"
        assert d["paradigm"] == "functional"
        assert d["cardinality"] == "many"

    def test_model_dump_json_plain_strings(self):
        import json

        m = self._Sample(
            direction=Direction.OUT,
            paradigm=Paradigm.DECLARATIVE,
            cardinality=Cardinality.ONE,
        )
        d = json.loads(m.model_dump_json())
        assert d["direction"] == "out"
        assert d["paradigm"] == "declarative"
        assert d["cardinality"] == "one"


# ---------------------------------------------------------------------------
# new_id uniqueness
# ---------------------------------------------------------------------------


class TestNewId:
    def test_returns_string(self):
        assert isinstance(new_id(), str)

    def test_uniqueness_over_100_calls(self):
        ids = [new_id() for _ in range(100)]
        assert len(set(ids)) == 100, "new_id() must return distinct values on every call"

    def test_non_empty(self):
        assert new_id() != ""

    def test_irId_is_str_alias(self):
        """IRId is a type alias for str."""
        _id: IRId = new_id()
        assert isinstance(_id, str)


# ---------------------------------------------------------------------------
# ArtifactRef validation
# ---------------------------------------------------------------------------


class TestArtifactRef:
    def test_valid_s3_uri(self):
        ref = ArtifactRef(uri="s3://my-bucket/path/to/file.parquet")
        assert ref.uri == "s3://my-bucket/path/to/file.parquet"
        assert ref.media_type is None

    def test_valid_with_media_type(self):
        ref = ArtifactRef(uri="s3://b/k", media_type="application/parquet")
        assert ref.media_type == "application/parquet"

    def test_valid_local_path(self):
        ref = ArtifactRef(uri="/data/artifacts/model.pkl")
        assert ref.uri == "/data/artifacts/model.pkl"

    def test_empty_uri_raises(self):
        with pytest.raises(ValidationError):
            ArtifactRef(uri="")

    def test_whitespace_only_uri_raises(self):
        with pytest.raises(ValidationError):
            ArtifactRef(uri="   ")

    def test_unknown_field_raises(self):
        with pytest.raises(ValidationError):
            ArtifactRef(uri="s3://b/k", unknown_field="should_fail")

    def test_no_bytes_field(self):
        """ArtifactRef must not expose a 'data' or 'bytes' field."""
        ref = ArtifactRef(uri="s3://b/k")
        dumped = ref.model_dump()
        assert "data" not in dumped
        assert "bytes" not in dumped
        assert "content" not in dumped


# ---------------------------------------------------------------------------
# IRModel base — extra=forbid
# ---------------------------------------------------------------------------


class TestIRModel:
    class _Concrete(IRModel):
        value: int

    def test_valid_construction(self):
        m = self._Concrete(value=42)
        assert m.value == 42

    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            self._Concrete(value=1, extra_key="nope")

    def test_validate_assignment(self):
        """validate_assignment=True means type errors on attribute set raise."""
        m = self._Concrete(value=10)
        with pytest.raises((ValidationError, ValueError)):
            m.value = "not-an-int"  # type: ignore[assignment]
