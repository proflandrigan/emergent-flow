"""Tests for ``emergentflow.data.load_excel`` (Epic 16 Story 3).

Fixture workbooks are built in-test with pandas rather than checking a binary
``.xlsx`` file into the repo.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("openpyxl")

from emergentflow.data import DataLoadError, load_excel  # noqa: E402
from emergentflow.data.errors import SchemaContractError  # noqa: E402


def test_load_excel_default_sheet(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(path, sheet_name="Sheet1", index=False)

    result = load_excel(str(path))

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_excel_by_sheet_name(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [3, 4]}).to_excel(writer, sheet_name="Second", index=False)

    result = load_excel(str(path), sheet="Second")

    assert list(result.columns) == ["b"]
    assert list(result["b"]) == [3, 4]


def test_load_excel_by_sheet_index(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [3, 4]}).to_excel(writer, sheet_name="Second", index=False)

    by_name = load_excel(str(path), sheet="Second")
    by_index = load_excel(str(path), sheet=1)

    assert by_name.equals(by_index)


def test_load_excel_missing_sheet_raises(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2]}).to_excel(path, sheet_name="Sheet1", index=False)

    with pytest.raises(DataLoadError) as exc_info:
        load_excel(str(path), sheet="NoSuchSheet")

    assert "NoSuchSheet" in str(exc_info.value)


def test_load_excel_header_row(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    frame = pd.DataFrame([["junk", "row"], ["a", "b"], [1, "x"], [2, "y"]])
    frame.to_excel(path, sheet_name="Sheet1", index=False, header=False)

    result = load_excel(str(path), header_row=1)

    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_excel_usecols(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(path, sheet_name="Sheet1", index=False)

    result = load_excel(str(path), usecols=["a"])

    assert list(result.columns) == ["a"]


def test_load_excel_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_excel("/nonexistent/path/to/file.xlsx")


def test_load_excel_empty_path_raises() -> None:
    with pytest.raises(ValueError):
        load_excel("")


def test_load_excel_sheet_none_raises(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2]}).to_excel(path, sheet_name="Sheet1", index=False)

    with pytest.raises(ValueError):
        load_excel(str(path), sheet=None)  # type: ignore[arg-type]


def test_load_excel_glob_concatenates(tmp_path: Path) -> None:
    pd.DataFrame({"a": [3]}).to_excel(tmp_path / "b.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"a": [1, 2]}).to_excel(tmp_path / "a.xlsx", sheet_name="Sheet1", index=False)

    result = load_excel(str(tmp_path / "*.xlsx"))

    assert list(result["a"]) == [1, 2, 3]


def test_load_excel_source_file_column(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2]}).to_excel(path, sheet_name="Sheet1", index=False)

    result = load_excel(str(path), source_file=True)

    assert "source_file" in result.columns
    assert (result["source_file"] == str(path)).all()


def test_load_excel_expect_columns_pass(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(path, sheet_name="Sheet1", index=False)

    result = load_excel(str(path), expect_columns=["a", "b"])

    assert list(result.columns) == ["a", "b"]


def test_load_excel_expect_columns_fail(tmp_path: Path) -> None:
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(path, sheet_name="Sheet1", index=False)

    with pytest.raises(SchemaContractError):
        load_excel(str(path), expect_columns=["a", "c"])


def test_load_excel_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.load_excel" in PUBLIC_OPS
