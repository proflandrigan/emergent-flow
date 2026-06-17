"""Tests for ``colonymind.data`` (Epic 1, Story 8)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from colonymind.data import load_csv


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
    from colonymind.api import PUBLIC_OPS

    assert "cm.data.load_csv" in PUBLIC_OPS


def test_load_csv_deterministic(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    first = load_csv(str(csv_path))
    second = load_csv(str(csv_path))

    assert first.equals(second)
