"""Tests for ``emergentflow.data.contract.validate_schema`` (Epic 16 Story 4)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.data.contract import validate_schema
from emergentflow.data.errors import DataLoadError, SchemaContractError


def test_no_contract_returns_frame_unchanged() -> None:
    frame = pd.DataFrame({"a": [1, 2]})

    result = validate_schema(frame)

    assert result is frame


def test_expect_columns_pass() -> None:
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    result = validate_schema(frame, expect_columns=["a", "b"])

    assert result is frame


def test_missing_column_raises_naming_all() -> None:
    frame = pd.DataFrame({"a": [1, 2]})

    with pytest.raises(SchemaContractError) as exc_info:
        validate_schema(frame, expect_columns=["a", "b", "c"])

    message = str(exc_info.value)
    assert "b" in message
    assert "c" in message
    assert "a" in message


def test_allow_extra_columns_false_raises() -> None:
    frame = pd.DataFrame({"a": [1], "b": [2], "extra": [3]})

    with pytest.raises(SchemaContractError, match="extra"):
        validate_schema(frame, expect_columns=["a", "b"], allow_extra_columns=False)


def test_dtype_expected_column_not_flagged_extra() -> None:
    """A column required via ``expect_dtypes`` must not be reported "extra" when
    ``allow_extra_columns=False`` even if omitted from ``expect_columns``."""
    frame = pd.DataFrame({"a": [1, 2], "b": [1.5, 2.5]})

    result = validate_schema(
        frame,
        expect_columns=["a"],
        expect_dtypes={"a": "int64", "b": "float64"},
        allow_extra_columns=False,
    )

    assert result is frame


def test_allow_extra_columns_true_by_default() -> None:
    frame = pd.DataFrame({"a": [1], "b": [2], "extra": [3]})

    result = validate_schema(frame, expect_columns=["a", "b"])

    assert result is frame


def test_expect_dtypes_pass() -> None:
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    result = validate_schema(frame, expect_dtypes={"a": "int64", "b": "object"})

    assert result is frame


def test_dtype_mismatch_raises_naming_expected_and_actual() -> None:
    frame = pd.DataFrame({"a": ["not", "ints"]})

    with pytest.raises(SchemaContractError) as exc_info:
        validate_schema(frame, expect_dtypes={"a": "int64"})

    message = str(exc_info.value)
    assert "int64" in message
    assert "object" in message


def test_dtype_on_missing_column_reported_as_missing() -> None:
    frame = pd.DataFrame({"a": [1, 2]})

    with pytest.raises(SchemaContractError, match="missing"):
        validate_schema(frame, expect_dtypes={"b": "int64"})


def test_all_categories_reported_in_one_error() -> None:
    frame = pd.DataFrame({"a": [1, 2], "extra": ["x", "y"]})

    with pytest.raises(SchemaContractError) as exc_info:
        validate_schema(
            frame,
            expect_columns=["a", "missing_col"],
            expect_dtypes={"a": "float64"},
            allow_extra_columns=False,
        )

    message = str(exc_info.value)
    assert "missing_col" in message
    assert "extra" in message
    assert "float64" in message


def test_error_is_data_load_error_subclass() -> None:
    frame = pd.DataFrame({"a": [1]})

    try:
        validate_schema(frame, expect_columns=["missing"])
    except DataLoadError:
        pass
    else:
        pytest.fail("expected SchemaContractError to be catchable as DataLoadError")

    try:
        validate_schema(frame, expect_columns=["missing"])
    except ValueError:
        pass
    else:
        pytest.fail("expected SchemaContractError to be catchable as ValueError")


def test_frame_not_mutated() -> None:
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    original_columns = list(frame.columns)
    original_values = frame.copy()

    validate_schema(frame, expect_columns=["a", "b"], expect_dtypes={"a": "int64"})

    assert list(frame.columns) == original_columns
    assert frame.equals(original_values)
