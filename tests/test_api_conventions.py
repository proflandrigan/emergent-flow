"""Tests for the SDK design-philosophy enforcement contract (Epic 1, Story 7).

Covers colonymind.api: is_inspectable / assert_inspectable / public_op / PUBLIC_OPS.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from colonymind.api import (
    PUBLIC_OPS,
    InspectableContractError,
    assert_inspectable,
    is_inspectable,
    public_op,
)

# --- fixtures: sanctioned + opaque return shapes -------------------------------


class _Result(BaseModel):
    p_value: float
    label: str


@dataclass
class _DataclassResult:
    f_statistic: float
    summary: list[dict[str, int]]


class _FakeDataFrame:
    """Duck-typed stand-in for a pandas/polars DataFrame (no real dep needed)."""

    shape = (2, 2)
    columns = ["a", "b"]

    def to_dict(self) -> dict[str, list[int]]:
        return {"a": [1, 2], "b": [3, 4]}


class _Opaque:
    """An opaque library-internal handle — the anti-pattern Story 7 forbids."""


def _gen() -> object:
    yield 1


# --- is_inspectable: accepted shapes -------------------------------------------


def test_scalars_are_inspectable() -> None:
    for value in (None, True, 0, 3.14, "x"):
        assert is_inspectable(value) is True


def test_pydantic_model_is_inspectable() -> None:
    assert is_inspectable(_Result(p_value=0.01, label="ok")) is True


def test_dataclass_instance_is_inspectable() -> None:
    assert is_inspectable(_DataclassResult(f_statistic=1.0, summary=[{"n": 3}])) is True


def test_dataclass_type_is_not_inspectable() -> None:
    # The class object itself is not a result value.
    assert is_inspectable(_DataclassResult) is False


def test_dataframe_like_is_inspectable() -> None:
    assert is_inspectable(_FakeDataFrame()) is True


def test_nested_container_of_inspectables_is_inspectable() -> None:
    assert is_inspectable({"rows": [1, 2, {"k": "v"}], "n": 3}) is True


# --- is_inspectable: rejected shapes -------------------------------------------


def test_opaque_object_is_not_inspectable() -> None:
    assert is_inspectable(_Opaque()) is False


def test_generator_is_not_inspectable() -> None:
    assert is_inspectable(_gen()) is False


def test_file_handle_is_not_inspectable() -> None:
    assert is_inspectable(io.StringIO("x")) is False


def test_bytes_are_not_inspectable() -> None:
    assert is_inspectable(b"raw") is False


def test_container_with_opaque_value_is_not_inspectable() -> None:
    assert is_inspectable({"ok": 1, "bad": _Opaque()}) is False


def test_dict_with_non_string_keys_is_not_inspectable() -> None:
    assert is_inspectable({1: "a"}) is False


# --- assert_inspectable --------------------------------------------------------


def test_assert_inspectable_passes_for_valid() -> None:
    assert assert_inspectable({"a": 1}) is None


def test_assert_inspectable_raises_for_opaque() -> None:
    with pytest.raises(InspectableContractError):
        assert_inspectable(_Opaque())


def test_assert_inspectable_message_names_location() -> None:
    with pytest.raises(InspectableContractError, match="cm.demo.op"):
        assert_inspectable(_Opaque(), where="cm.demo.op")


def test_contract_error_is_a_type_error() -> None:
    assert issubclass(InspectableContractError, TypeError)


# --- public_op decorator + registry --------------------------------------------


def test_public_op_allows_inspectable_return() -> None:
    @public_op(name="test.compliant_op")
    def compliant() -> dict[str, int]:
        return {"value": 1}

    assert compliant() == {"value": 1}
    assert "test.compliant_op" in PUBLIC_OPS
    assert getattr(PUBLIC_OPS["test.compliant_op"], "__cm_public_op__", False) is True


def test_public_op_flags_opaque_return() -> None:
    @public_op(name="test.opaque_op")
    def offender() -> object:
        return _Opaque()

    with pytest.raises(InspectableContractError):
        offender()


def test_public_op_bare_form_registers_under_qualname() -> None:
    @public_op
    def bare_form() -> int:
        return 7

    assert bare_form() == 7
    assert any(key.endswith("bare_form") for key in PUBLIC_OPS)


def test_public_op_preserves_metadata() -> None:
    @public_op
    def documented() -> int:
        """A documented op."""
        return 1

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "A documented op."


def test_registered_ops_are_all_marked() -> None:
    # Sweep the catalog: every registered op must carry the marker. This is the
    # mechanism a future Story-8 wrapper sweep relies on.
    for op in PUBLIC_OPS.values():
        assert getattr(op, "__cm_public_op__", False) is True
