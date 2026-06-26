"""Tests for emergentflow.ir.params — typed parameter model."""

import json

import pytest
from pydantic import ValidationError

from emergentflow.ir.common import ArtifactRef
from emergentflow.ir.params import Param

# ---------------------------------------------------------------------------
# Scalar round-trip
# ---------------------------------------------------------------------------


class TestScalarRoundTrip:
    def test_string_value_valid(self):
        p = Param(name="strategy", type_token="str", value="median")
        assert p.value == "median"

    def test_int_value_valid(self):
        p = Param(name="epochs", type_token="int", value=10)
        assert p.value == 10

    def test_float_value_valid(self):
        p = Param(name="lr", type_token="float", value=0.001)
        assert p.value == pytest.approx(0.001)

    def test_bool_value_valid(self):
        p = Param(name="verbose", type_token="bool", value=True)
        assert p.value is True

    def test_none_value_valid(self):
        p = Param(name="threshold", type_token="float", value=None)
        assert p.value is None

    def test_json_round_trip(self):
        """model_dump_json / model_validate_json must be lossless."""
        original = Param(name="strategy", type_token="str", value="median")
        reloaded = Param.model_validate_json(original.model_dump_json())
        assert reloaded == original

    def test_default_field(self):
        p = Param(name="k", type_token="int", value=5, default=3)
        assert p.default == 3

    def test_value_defaults_to_none(self):
        p = Param(name="x", type_token="str")
        assert p.value is None
        assert p.default is None


# ---------------------------------------------------------------------------
# Nested dict / list value
# ---------------------------------------------------------------------------


class TestNestedValue:
    def test_nested_dict_list(self):
        p = Param(name="opts", type_token="dict", value={"a": [1, 2], "b": {"c": True}})
        assert p.value == {"a": [1, 2], "b": {"c": True}}

    def test_nested_json_round_trip(self):
        original = Param(
            name="opts",
            type_token="dict",
            value={"a": [1, 2], "b": {"c": True}},
        )
        reloaded = Param.model_validate_json(original.model_dump_json())
        assert reloaded == original

    def test_list_of_scalars(self):
        p = Param(name="tags", type_token="list", value=["a", "b", "c"])
        assert p.value == ["a", "b", "c"]

    def test_deeply_nested(self):
        value = {"outer": {"inner": [1, {"deep": None}]}}
        p = Param(name="cfg", type_token="dict", value=value)
        assert p.value == value


# ---------------------------------------------------------------------------
# ArtifactRef value
# ---------------------------------------------------------------------------


class TestArtifactRefValue:
    def test_artifact_ref_as_value(self):
        ref = ArtifactRef(uri="s3://b/f.parquet")
        p = Param(name="frame", type_token="DataFrame", value=ref)
        assert isinstance(p.value, ArtifactRef)
        assert p.value.uri == "s3://b/f.parquet"

    def test_artifact_ref_json_round_trip(self):
        ref = ArtifactRef(uri="s3://b/f.parquet", media_type="application/parquet")
        original = Param(name="frame", type_token="DataFrame", value=ref)
        reloaded = Param.model_validate_json(original.model_dump_json())
        assert reloaded == original

    def test_artifact_ref_as_default(self):
        ref = ArtifactRef(uri="s3://b/default.parquet")
        p = Param(name="frame", type_token="DataFrame", default=ref)
        assert isinstance(p.default, ArtifactRef)

    def test_artifact_ref_construction_stays_ergonomic(self):
        """The discriminator tag defaults, so ArtifactRef(uri=...) needs no kind."""
        ref = ArtifactRef(uri="s3://b/k")
        assert ref.kind == "artifact_ref"

    def test_artifact_ref_emits_discriminator_tag(self):
        """A serialized ArtifactRef carries kind='artifact_ref'."""
        p = Param(name="frame", type_token="DataFrame", value=ArtifactRef(uri="s3://b/k"))
        dumped = json.loads(p.model_dump_json())
        assert dumped["value"]["kind"] == "artifact_ref"

    def test_plain_dict_shaped_like_artifact_ref_stays_dict(self):
        """A plain mapping that happens to share ArtifactRef's shape must NOT be
        coerced into an ArtifactRef — the discriminator keeps the round-trip lossless.
        """
        value = {"uri": "http://example.com/webhook", "media_type": "application/json"}
        original = Param(name="cfg", type_token="dict", value=value)
        assert isinstance(original.value, dict)
        reloaded = Param.model_validate_json(original.model_dump_json())
        assert isinstance(reloaded.value, dict)
        assert reloaded == original
        assert reloaded.value == value

    def test_nested_artifact_ref_round_trip(self):
        """ArtifactRefs nested inside lists/dicts survive a round-trip as ArtifactRefs."""
        original = Param(
            name="frames",
            type_token="list",
            value=[ArtifactRef(uri="s3://a"), {"plain": {"uri": "not-an-artifact"}}],
        )
        reloaded = Param.model_validate_json(original.model_dump_json())
        assert isinstance(reloaded.value[0], ArtifactRef)
        assert isinstance(reloaded.value[1], dict)
        assert isinstance(reloaded.value[1]["plain"], dict)
        assert reloaded == original


# ---------------------------------------------------------------------------
# Validation rejections
# ---------------------------------------------------------------------------


class TestValidationRejections:
    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            Param(name="", type_token="str")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValidationError):
            Param(name="   ", type_token="str")

    def test_empty_type_token_raises(self):
        with pytest.raises(ValidationError):
            Param(name="x", type_token="")

    def test_whitespace_only_type_token_raises(self):
        with pytest.raises(ValidationError):
            Param(name="x", type_token="   ")

    def test_set_value_coerces_to_serializable_list(self):
        """A set is not a native value type; Pydantic lax-coerces it to a list,
        which remains JSON-serializable (the contract is serializability, not
        identity preservation of sets)."""
        p = Param(name="x", type_token="x", value={1, 2})
        assert isinstance(p.value, list)
        assert sorted(p.value) == [1, 2]
        # round-trips through JSON without error
        Param.model_validate_json(p.model_dump_json())

    def test_arbitrary_object_raises(self):
        """An arbitrary Python object must be rejected as a value."""

        class _Unserializable:
            pass

        with pytest.raises((ValidationError, TypeError)):
            Param(name="x", type_token="x", value=_Unserializable())

    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            Param(name="x", type_token="str", unknown_field="nope")


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


class TestImports:
    def test_param_importable(self):
        from emergentflow.ir.params import Param as _Param  # noqa: F401

    def test_param_value_importable(self):
        from emergentflow.ir.params import ParamValue as _ParamValue  # noqa: F401
