"""Tests for remote object-storage URI loading (Epic 16) via fsspec.

Every test here is offline: fsspec's built-in in-memory filesystem
(``fsspec.filesystem("memory")``, URI scheme ``memory://``) stands in for a real
object store, so nothing touches the network or needs cloud credentials.
``memory://`` is registered in ``emergentflow.data.REMOTE_URI_SCHEMES`` as a
deliberate test seam for exactly this purpose.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

fsspec = pytest.importorskip("fsspec")

from emergentflow.data import (  # noqa: E402
    DataLoadError,
    _is_remote_uri,
    load_csv,
    load_json,
    load_parquet,
)


def _memfs() -> object:
    return fsspec.filesystem("memory")


def test_remote_uri_detected() -> None:
    assert _is_remote_uri("s3://b/k.csv") is True
    assert _is_remote_uri("/local/k.csv") is False


def test_load_csv_from_memory_filesystem() -> None:
    fs = _memfs()
    with fs.open("/csv_single/data.csv", "wb") as fh:
        fh.write(b"a,b\n1,x\n2,y\n")

    result = load_csv("memory://csv_single/data.csv")

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_csv_remote_glob_concatenates() -> None:
    fs = _memfs()
    with fs.open("/csv_glob/a.csv", "wb") as fh:
        fh.write(b"a,b\n1,x\n")
    with fs.open("/csv_glob/b.csv", "wb") as fh:
        fh.write(b"a,b\n2,y\n")

    result = load_csv("memory://csv_glob/*.csv")

    assert list(result.columns) == ["a", "b"]
    assert sorted(result["a"].tolist()) == [1, 2]
    assert result.shape == (2, 2)


def test_load_csv_remote_glob_no_matches_raises() -> None:
    with pytest.raises(DataLoadError, match="memory://csv_missing/\\*.csv"):
        load_csv("memory://csv_missing/*.csv")


def test_load_csv_remote_source_file_column() -> None:
    fs = _memfs()
    with fs.open("/csv_source/data.csv", "wb") as fh:
        fh.write(b"a,b\n1,x\n2,y\n")

    result = load_csv("memory://csv_source/data.csv", source_file=True)

    assert "source_file" in result.columns
    assert (result["source_file"].str.startswith("memory://")).all()


def test_load_json_from_memory_filesystem() -> None:
    fs = _memfs()
    with fs.open("/json_single/data.json", "wb") as fh:
        fh.write(b'[{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]')

    result = load_json("memory://json_single/data.json")

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_load_parquet_from_memory_filesystem() -> None:
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    buffer = frame.to_parquet()

    fs = _memfs()
    with fs.open("/parquet_single/data.parquet", "wb") as fh:
        fh.write(buffer)

    result = load_parquet("memory://parquet_single/data.parquet")

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)


def test_local_path_unaffected(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    result = load_csv(str(csv_path))

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)
