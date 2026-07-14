"""Tests for ``emergentflow.data`` (Epic 1, Story 8)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from emergentflow.data import load_csv, load_json, load_parquet, load_sample


def test_load_csv_returns_dataframe(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    result = load_csv(str(csv_path))

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_csv_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_csv("/nonexistent/path/to/file.csv")


def test_load_csv_empty_path_raises() -> None:
    with pytest.raises(ValueError):
        load_csv("")


def test_load_csv_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.load_csv" in PUBLIC_OPS


def test_load_csv_deterministic(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    first = load_csv(str(csv_path))
    second = load_csv(str(csv_path))

    assert first.equals(second)


def test_load_parquet_returns_dataframe(tmp_path: Path) -> None:
    parquet_path = tmp_path / "d.parquet"
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df.to_parquet(parquet_path)

    result = load_parquet(str(parquet_path))

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_parquet_columns_subset(tmp_path: Path) -> None:
    parquet_path = tmp_path / "d.parquet"
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"], "c": [3, 4]})
    df.to_parquet(parquet_path)

    result = load_parquet(str(parquet_path), columns=["a"])

    assert list(result.columns) == ["a"]
    assert result.shape == (2, 1)


def test_load_parquet_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_parquet("/nonexistent/path/to/file.parquet")


def test_load_parquet_empty_path_raises() -> None:
    with pytest.raises(ValueError):
        load_parquet("")


def test_load_parquet_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.load_parquet" in PUBLIC_OPS


def test_load_json_returns_dataframe(tmp_path: Path) -> None:
    json_path = tmp_path / "d.json"
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df.to_json(json_path, orient="records")

    result = load_json(str(json_path), orient="records")

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_json_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_json("/nonexistent/path/to/file.json")


def test_load_json_empty_path_raises() -> None:
    with pytest.raises(ValueError):
        load_json("")


def test_load_json_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.load_json" in PUBLIC_OPS


def test_load_json_lines_reads_jsonl(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "d.jsonl"
    jsonl_path.write_text('{"a": 1, "b": "x"}\n{"a": 2, "b": "y"}\n')

    result = load_json(str(jsonl_path), lines=True)

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_sample_default_returns_dataframe_with_target() -> None:
    result = load_sample()

    assert isinstance(result, pd.DataFrame)
    assert "target" in result.columns
    assert result.shape[0] > 0


def test_load_sample_diabetes_returns_dataframe_with_target() -> None:
    result = load_sample("diabetes")

    assert isinstance(result, pd.DataFrame)
    assert "target" in result.columns
    assert result.shape[0] > 0


def test_load_sample_unknown_name_raises() -> None:
    with pytest.raises(ValueError):
        load_sample("not-a-real-dataset")


def test_load_sample_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.load_sample" in PUBLIC_OPS


def test_load_sample_deterministic() -> None:
    first = load_sample()
    second = load_sample()

    assert first.equals(second)
