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
    assert (d / "g=a" / "data.csv").is_file()
    assert (d / "g=b" / "data.csv").is_file()


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
