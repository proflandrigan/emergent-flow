"""Tests for `ef.data.save_frame` (issue #164 Gap 6) and its reference node.

Covers the chainable pass-through contract, format round-trips, ``mode="error"``
clobber protection, Hive partitioning, and the node's ADR-0002 equivalence.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.data import DataError, save_frame


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})


def test_save_frame_is_chainable(frame, tmp_path):
    out = save_frame(frame, path=str(tmp_path / "o.parquet"))
    pd.testing.assert_frame_equal(out, frame)  # returns the same frame unchanged


def test_save_frame_parquet_round_trip(frame, tmp_path):
    p = tmp_path / "o.parquet"
    save_frame(frame, path=str(p))
    pd.testing.assert_frame_equal(pd.read_parquet(p), frame)


def test_save_frame_csv_round_trip(frame, tmp_path):
    p = tmp_path / "o.csv"
    save_frame(frame, path=str(p), format="csv")
    pd.testing.assert_frame_equal(pd.read_csv(p), frame)


def test_save_frame_mode_error_raises_on_existing(frame, tmp_path):
    p = tmp_path / "o.parquet"
    save_frame(frame, path=str(p))
    with pytest.raises(DataError, match="overwrite"):
        save_frame(frame, path=str(p), mode="error")


def test_save_frame_unknown_format_raises(frame, tmp_path):
    with pytest.raises(DataError, match="format"):
        save_frame(frame, path=str(tmp_path / "o.x"), format="xlsx")


def test_save_frame_partition_by(frame, tmp_path):
    df = frame.assign(g=["a", "a", "b"])
    d = tmp_path / "part"
    save_frame(df, path=str(d), format="csv", partition_by=["g"])
    assert (d / "g=a").is_dir()
    assert any((d / "g=a").glob("part-*.csv"))


def test_save_frame_unknown_partition_column_raises(frame, tmp_path):
    with pytest.raises(DataError, match="partition_by"):
        save_frame(frame, path=str(tmp_path / "part"), partition_by=["nope"])


def test_save_frame_registered_as_public_op():
    from emergentflow.api import PUBLIC_OPS

    assert "ef.data.save_frame" in PUBLIC_OPS


def test_save_frame_node_codegen_equivalence(frame, tmp_path):
    from emergentflow.nodes.examples.save_frame import SaveFrame

    p = str(tmp_path / "o.parquet")
    defn = SaveFrame()
    node = defn.instantiate(path=p)
    executed = defn.execute(node, inputs={"frame": frame.copy()})["result"]
    scope = {"frame": frame.copy()}
    exec(defn.preview(node).render(), scope)  # noqa: S102 - test-only on our own code
    pd.testing.assert_frame_equal(executed, scope["result"])
    pd.testing.assert_frame_equal(pd.read_parquet(p), frame)


def _leaf_files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("part-*.parquet"))


def test_save_frame_overwrite_removes_stale_partitions(frame, tmp_path):
    d = tmp_path / "part"
    save_frame(frame.assign(g=["x", "x", "y"]), path=str(d), partition_by=["g"])
    assert {p.name for p in d.iterdir()} == {"g=x", "g=y"}
    save_frame(frame.iloc[:1].assign(g=["z"]), path=str(d), partition_by=["g"])
    assert {p.name for p in d.iterdir()} == {"g=z"}
    assert len(pd.read_parquet(d)) == 1


def test_save_frame_partition_values_are_escaped(frame, tmp_path):
    d = tmp_path / "out"
    df = frame.assign(g=["../../../outside/pwned", "sub/dir", "a b"])
    save_frame(df, path=str(d), partition_by=["g"])
    assert not (tmp_path / "outside").exists()
    assert all(p.startswith("g=") and "/" not in p.split("/", 1)[0][2:] for p in _leaf_files(d))
    assert (d / "g=sub%2Fdir").is_dir()
    back = pd.read_parquet(d)
    assert sorted(back["g"].astype(str)) == sorted(df["g"])


def test_save_frame_null_partition_does_not_collide_with_nan_string(frame, tmp_path):
    import pyarrow.dataset as ds

    d = tmp_path / "out"
    save_frame(frame.assign(g=["nan", None, "x"]), path=str(d), partition_by=["g"])
    assert {p.name for p in d.iterdir()} == {"g=nan", "g=__HIVE_DEFAULT_PARTITION__", "g=x"}
    table = ds.dataset(str(d), partitioning="hive").to_table()
    assert table.num_rows == 3
    assert sorted(table.column("g").to_pylist(), key=str) == sorted(["nan", None, "x"], key=str)


def test_save_frame_rejects_partitioning_every_column_and_bare_string(frame, tmp_path):
    with pytest.raises(DataError, match="every column"):
        save_frame(frame, path=str(tmp_path / "p"), partition_by=["a", "b"])
    with pytest.raises(DataError, match="list of column names"):
        save_frame(frame, path=str(tmp_path / "p"), partition_by="ab")  # type: ignore[arg-type]


def test_save_frame_expands_home(frame, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    save_frame(frame, path="~/o.csv", format="csv")
    assert (tmp_path / "o.csv").is_file()
    assert not (tmp_path / "~").exists()
    with pytest.raises(DataError, match="overwrite"):
        save_frame(frame, path="~/o.csv", format="csv", mode="error")


def test_save_frame_remote_uri_requires_cloud_extra(frame, monkeypatch):
    import importlib.util

    from emergentflow.data import MissingOptionalDependencyError

    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    with pytest.raises(MissingOptionalDependencyError, match="cloud"):
        save_frame(frame, path="s3://bucket/o.parquet")


def test_save_frame_json_round_trips_through_load_json(frame, tmp_path):
    from emergentflow.data import load_json

    p = tmp_path / "o.json"
    save_frame(frame, path=str(p), format="json")
    pd.testing.assert_frame_equal(load_json(str(p), lines=True), frame)


def test_save_frame_file_directory_mismatches_are_typed(frame, tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    with pytest.raises(DataError, match="directory"):
        save_frame(frame, path=str(d))
    f = tmp_path / "file.parquet"
    save_frame(frame, path=str(f))
    with pytest.raises(DataError, match="file"):
        save_frame(frame.assign(g=[1, 1, 2]), path=str(f), partition_by=["g"])


def test_save_frame_keeps_a_meaningful_index(frame, tmp_path):
    idx = pd.date_range("2024-01-01", periods=3, freq="D", name="ts")
    dated = frame.set_index(idx)
    p = tmp_path / "dated.parquet"
    save_frame(dated, path=str(p))
    pd.testing.assert_frame_equal(pd.read_parquet(p), dated, check_freq=False)  # freq isn't stored
    c = tmp_path / "dated.csv"
    save_frame(dated, path=str(c), format="csv")
    assert list(pd.read_csv(c).columns) == ["ts", "a", "b"]
    plain = tmp_path / "plain.parquet"
    save_frame(frame, path=str(plain))  # a RangeIndex is still dropped
    assert list(pd.read_parquet(plain).columns) == ["a", "b"]
    forced = tmp_path / "forced.csv"
    save_frame(dated, path=str(forced), format="csv", index=False)
    assert list(pd.read_csv(forced).columns) == ["a", "b"]


def test_effectful_nodes_are_not_cacheable():
    from emergentflow.nodes.examples.save_frame import SaveFrame
    from emergentflow.nodes.examples.write_table import WriteTable

    assert SaveFrame.cacheable is False
    assert WriteTable.cacheable is False
