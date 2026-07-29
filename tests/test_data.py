"""Tests for ``emergentflow.data`` (Epic 1, Story 8)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from emergentflow.data import (
    SAMPLE_DATASETS,
    DataLoadError,
    load_csv,
    load_json,
    load_parquet,
    load_sample,
)
from emergentflow.data.errors import SchemaContractError


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


def test_load_csv_glob_concatenates_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.csv").write_text("a,b\n3,z\n")
    (tmp_path / "a.csv").write_text("a,b\n1,x\n2,y\n")

    result = load_csv(str(tmp_path / "*.csv"))

    assert list(result["a"]) == [1, 2, 3]


def test_load_csv_glob_adds_source_file_column(tmp_path: Path) -> None:
    a_path = tmp_path / "a.csv"
    b_path = tmp_path / "b.csv"
    a_path.write_text("a,b\n1,x\n")
    b_path.write_text("a,b\n2,y\n")

    result = load_csv(str(tmp_path / "*.csv"), source_file=True)

    assert "source_file" in result.columns
    assert set(result["source_file"]) == {str(a_path), str(b_path)}


def test_load_csv_glob_no_matches_raises(tmp_path: Path) -> None:
    pattern = str(tmp_path / "*.csv")

    with pytest.raises(DataLoadError, match=r".*\*\.csv.*"):
        load_csv(pattern)


def test_load_csv_glob_aligns_differing_schemas(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("a,b\n1,x\n")
    (tmp_path / "b.csv").write_text("a,c\n2,y\n")

    result = load_csv(str(tmp_path / "*.csv"))

    assert set(result.columns) == {"a", "b", "c"}
    assert list(result.index) == list(range(len(result)))


def test_load_csv_single_file_unchanged(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    result = load_csv(str(csv_path))

    assert list(result.columns) == ["a", "b"]
    assert result.shape == (2, 2)

    with pytest.raises(FileNotFoundError):
        load_csv(str(tmp_path / "missing.csv"))


def test_load_csv_source_file_on_single_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    result = load_csv(str(csv_path), source_file=True)

    assert "source_file" in result.columns
    assert set(result["source_file"]) == {str(csv_path)}


def test_load_csv_source_file_collision_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,source_file\n1,existing\n")

    with pytest.raises(DataLoadError):
        load_csv(str(csv_path), source_file=True)


def test_glob_matches_directories_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("a,b\n1,x\n")
    (tmp_path / "sub.csv").mkdir()

    result = load_csv(str(tmp_path / "*.csv"))

    assert list(result["a"]) == [1]


def test_load_csv_expect_columns_pass(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    result = load_csv(str(csv_path), expect_columns=["a", "b"])

    assert list(result.columns) == ["a", "b"]


def test_load_csv_expect_columns_fail(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    with pytest.raises(SchemaContractError):
        load_csv(str(csv_path), expect_columns=["a", "c"])


def test_load_csv_expect_dtypes_fail(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,x\n2,y\n")

    with pytest.raises(SchemaContractError):
        load_csv(str(csv_path), expect_dtypes={"a": "float64"})


def test_load_csv_glob_contract_checked_on_concatenated_frame(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("a\n1\n2\n")
    (tmp_path / "b.csv").write_text("a,b\n3,x\n")

    result = load_csv(str(tmp_path / "*.csv"), expect_columns=["a", "b"])

    assert set(result.columns) == {"a", "b"}


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


def test_load_parquet_glob_concatenates(tmp_path: Path) -> None:
    df_a = pd.DataFrame({"a": [1], "b": ["x"]})
    df_b = pd.DataFrame({"a": [2], "b": ["y"]})
    df_a.to_parquet(tmp_path / "a.parquet")
    df_b.to_parquet(tmp_path / "b.parquet")

    result = load_parquet(str(tmp_path / "*.parquet"))

    assert list(result["a"]) == [1, 2]


def test_load_parquet_glob_no_matches_raises(tmp_path: Path) -> None:
    pattern = str(tmp_path / "*.parquet")

    with pytest.raises(DataLoadError, match=r".*\*\.parquet.*"):
        load_parquet(pattern)


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


def test_load_json_glob_concatenates(tmp_path: Path) -> None:
    df_a = pd.DataFrame({"a": [1], "b": ["x"]})
    df_b = pd.DataFrame({"a": [2], "b": ["y"]})
    df_a.to_json(tmp_path / "a.json", orient="records")
    df_b.to_json(tmp_path / "b.json", orient="records")

    result = load_json(str(tmp_path / "*.json"), orient="records")

    assert list(result["a"]) == [1, 2]


def test_load_json_glob_no_matches_raises(tmp_path: Path) -> None:
    pattern = str(tmp_path / "*.json")

    with pytest.raises(DataLoadError, match=r".*\*\.json.*"):
        load_json(pattern)


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


def test_load_sample_new_datasets_registered() -> None:
    for name in ("web_traffic", "reviews", "transactions"):
        assert name in SAMPLE_DATASETS


def test_load_sample_web_traffic_shape() -> None:
    result = load_sample("web_traffic")

    assert result.shape[0] == 365
    assert list(result.columns) == ["date", "sessions", "conversions", "channel"]
    assert pd.api.types.is_datetime64_any_dtype(result["date"])
    assert pd.api.types.is_integer_dtype(result["sessions"])
    assert pd.api.types.is_integer_dtype(result["conversions"])
    assert (result["sessions"] >= 0).all()
    assert (result["conversions"] >= 0).all()


def test_load_sample_reviews_shape() -> None:
    result = load_sample("reviews")

    assert result.shape[0] == 200
    assert list(result.columns) == ["review_id", "text", "rating", "category", "verified"]
    assert result["rating"].between(1, 5).all()
    assert result["text"].map(lambda t: isinstance(t, str) and len(t) > 0).all()


def test_load_sample_transactions_shape() -> None:
    result = load_sample("transactions")

    assert result.shape[0] == 500
    assert list(result.columns) == [
        "transaction_id",
        "customer_id",
        "timestamp",
        "amount",
        "product_category",
        "event",
    ]
    assert (result["amount"] > 0).all()
    assert set(result["event"].unique()) <= {"view", "add_to_cart", "purchase"}
    assert result["timestamp"].is_monotonic_increasing


def test_load_sample_transactions_has_repeat_customers() -> None:
    result = load_sample("transactions")

    assert result["customer_id"].nunique() < len(result) // 2


@pytest.mark.parametrize("name", ["web_traffic", "reviews", "transactions"])
def test_generated_samples_are_deterministic(name: str) -> None:
    first = load_sample(name)
    second = load_sample(name)

    pd.testing.assert_frame_equal(first, second)


def test_load_sample_unknown_name_still_raises() -> None:
    with pytest.raises(ValueError, match=r".*iris.*wine.*diabetes.*"):
        load_sample("not-a-real-dataset")


def test_existing_samples_unchanged() -> None:
    result = load_sample("iris")

    assert isinstance(result, pd.DataFrame)
    assert "target" in result.columns


def test_generated_sample_stable_across_processes() -> None:
    in_process_digest = str(int(pd.util.hash_pandas_object(load_sample("web_traffic")).sum()))

    snippet = (
        "import pandas as pd; "
        "from emergentflow.data import load_sample; "
        "df = load_sample('web_traffic'); "
        "print(str(int(pd.util.hash_pandas_object(df).sum())))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess_digest = completed.stdout.strip()

    assert subprocess_digest == in_process_digest
