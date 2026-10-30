"""Tests for POST /browse/frame (issue #178): browse the full stored DataFrame, not the preview."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from emergentflow.server import app, browse
from emergentflow.server.artifacts import ArtifactStore

N = 1200


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ArtifactStore:
    s = ArtifactStore(root=tmp_path / "art", max_mb=64)
    monkeypatch.setattr(browse, "get_default_artifacts", lambda: s)
    return s


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "term": [f"term_{i}" for i in range(N)],
            "score": [float(i % 10) for i in range(N)],  # heavy duplicates
            "n": list(range(N)),
        }
    )


def _put(store: ArtifactStore, frame: Any = None, node_id: str = "n1") -> str:
    return store.put(node_id, {"frame": _frame() if frame is None else frame})


def _post(client: TestClient, **body: Any) -> Any:
    return client.post("/browse/frame", json={"node_id": "n1", **body})


def test_defaults_and_counts(store: ArtifactStore, client: TestClient) -> None:
    rev = _put(store)
    body = _post(client, revision=rev).json()
    assert body["status"] == "ok"
    assert body["revision"] == rev
    assert body["total_rows"] == N == body["filtered_rows"]
    assert (body["offset"], body["limit"], len(body["rows"])) == (0, 100, 100)
    assert body["columns"] == ["term", "score", "n"]
    assert body["dtypes"][1:] == ["float64", "int64"]
    assert [r["_row"] for r in body["rows"]] == list(range(100))


def test_filter_finds_unique_row_beyond_preview(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    body = _post(
        client, filters=[{"column": "term", "operator": "==", "value": "term_1111"}]
    ).json()
    assert body["filtered_rows"] == 1 and body["total_rows"] == N
    assert body["rows"][0]["_row"] == 1111 and body["rows"][0]["n"] == 1111


def test_numeric_value_coerced_from_string(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    body = _post(client, filters=[{"column": "n", "operator": ">=", "value": "1195"}]).json()
    assert body["filtered_rows"] == 5
    body = _post(client, filters=[{"column": "n", "operator": "isin", "value": ["3", 900]}]).json()
    assert sorted(r["n"] for r in body["rows"]) == [3, 900]


def test_sort_returns_global_extremum(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    body = _post(client, sort=[{"column": "n", "ascending": False}], limit=3).json()
    assert [r["n"] for r in body["rows"]] == [N - 1, N - 2, N - 3]


def test_pagination_stable_with_duplicate_sort_keys(
    store: ArtifactStore, client: TestClient
) -> None:
    _put(store)
    seen: list[int] = []
    for offset in range(0, N, 500):
        page = _post(
            client, sort=[{"column": "score", "ascending": False}], offset=offset, limit=500
        )
        seen += [r["_row"] for r in page.json()["rows"]]
    assert sorted(seen) == list(range(N))  # no dupes, none lost
    scores = [_frame()["score"][i] for i in seen]
    assert scores == sorted(scores, reverse=True)
    # ties keep original positional order
    nines = [i for i in seen if i % 10 == 9]
    assert nines == sorted(nines)


def test_projection_and_row_index(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    body = _post(client, columns=["n"], limit=2, offset=10).json()
    assert body["columns"] == ["n"] and len(body["dtypes"]) == 1
    assert body["rows"] == [{"n": 10, "_row": 10}, {"n": 11, "_row": 11}]


def test_filter_then_sort_then_slice(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    body = _post(
        client,
        filters=[{"column": "score", "operator": "==", "value": 3}],
        sort=[{"column": "n", "ascending": False}],
        limit=2,
    ).json()
    assert body["filtered_rows"] == N // 10
    assert [r["n"] for r in body["rows"]] == [1193, 1183]


def test_nan_and_inf_cells_are_json_safe(store: ArtifactStore, client: TestClient) -> None:
    frame = pd.DataFrame({"x": [1.0, np.nan, np.inf, -np.inf], "s": ["a", None, "c", "d"]})
    _put(store, frame)
    resp = _post(client)
    assert resp.status_code == 200
    xs = [r["x"] for r in resp.json()["rows"]]
    assert xs == [1.0, None, None, None]
    srt = _post(client, sort=[{"column": "x", "ascending": True}]).json()
    assert [r["_row"] for r in srt["rows"]] == [3, 0, 2, 1]  # -inf, 1.0, +inf, NaN last


def test_wide_cells_truncated(store: ArtifactStore, client: TestClient) -> None:
    frame = pd.DataFrame({"vec": [list(range(500))], "t": ["x" * 1000]})
    _put(store, frame)
    row = _post(client).json()["rows"][0]
    assert len(row["vec"]) <= browse.MAX_CELL_CHARS + 1 and row["vec"].endswith("…")
    assert len(row["t"]) == browse.MAX_CELL_CHARS + 1


def test_expired_when_missing(store: ArtifactStore, client: TestClient) -> None:
    resp = _post(client, revision="r")
    assert resp.status_code == 200 and resp.json() == {"status": "expired"}


def test_revision_mismatch(store: ArtifactStore, client: TestClient) -> None:
    old = _put(store)
    new = _put(store)
    body = _post(client, revision=old).json()
    assert body == {"status": "revision_mismatch", "current_revision": new}


def test_not_tabular(store: ArtifactStore, client: TestClient) -> None:
    store.put("n1", {"frame": 3})
    assert _post(client).json()["status"] == "not_tabular"


@pytest.mark.parametrize(
    "extra",
    [
        {"filters": [{"column": "nope", "operator": "==", "value": 1}]},
        {"filters": [{"column": "n", "operator": "like", "value": 1}]},
        {"filters": [{"column": "n", "operator": "==", "value": "abc"}]},
        {"sort": [{"column": "nope"}]},
        {"columns": ["nope"]},
        {"offset": -1},
        {"limit": 0},
    ],
)
def test_bad_requests_422(store: ArtifactStore, client: TestClient, extra: dict[str, Any]) -> None:
    _put(store)
    resp = _post(client, **extra)
    assert resp.status_code == 422
    assert isinstance(resp.json()["error"], str)


def test_limit_is_capped(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    body = _post(client, limit=100000).json()
    assert body["limit"] == browse.MAX_LIMIT == len(body["rows"])


def test_non_string_column_labels(store: ArtifactStore, client: TestClient) -> None:
    # int labels (from an ndarray / a pivot on years) and MultiIndex tuples are addressed by
    # their stringified name, matching the 50-row preview's ``str(label)`` keys.
    _put(
        store,
        pd.DataFrame({"a": [1, 2, 3], "b": [30, 10, 20]}).rename(columns={"a": 2020, "b": 2021}),
    )
    body = _post(
        client,
        filters=[{"column": "2020", "operator": ">", "value": 1}],
        sort=[{"column": "2021", "ascending": True}],
        columns=["2021"],
    ).json()
    assert body["columns"] == ["2021"] and body["dtypes"] == ["int64"]
    assert body["rows"] == [{"2021": 10, "_row": 1}, {"2021": 20, "_row": 2}]
    multi = pd.DataFrame(
        [[1, 2], [3, 4]], columns=pd.MultiIndex.from_tuples([("x", "a"), ("x", "b")])
    )
    _put(store, multi)
    body = _post(client, filters=[{"column": "('x', 'b')", "operator": "==", "value": 4}]).json()
    assert body["columns"] == ["('x', 'a')", "('x', 'b')"]
    assert body["rows"] == [{"('x', 'a')": 3, "('x', 'b')": 4, "_row": 1}]


def test_duplicate_column_names(store: ArtifactStore, client: TestClient) -> None:
    _put(store, pd.DataFrame([[1, 2.5, "s"]], columns=["a", "a", "b"]))
    body = _post(client).json()
    assert body["status"] == "ok"
    assert body["columns"] == ["a", "a", "b"] and body["dtypes"] == ["int64", "float64", "object"]
    # Filtering / sorting / projecting by the ambiguous name is a clear 422, not a crash.
    for extra in (
        {"filters": [{"column": "a", "operator": "==", "value": 1}]},
        {"sort": [{"column": "a"}]},
        {"columns": ["a"]},
    ):
        resp = _post(client, **extra)
        assert resp.status_code == 422 and "ambiguous" in resp.json()["error"]
    assert _post(client, sort=[{"column": "b"}]).status_code == 200


def test_large_int_filter_is_exact(store: ArtifactStore, client: TestClient) -> None:
    big = 2**62
    _put(store, pd.DataFrame({"x": [big, big + 1]}))
    for value in (big + 1, str(big + 1)):
        body = _post(client, filters=[{"column": "x", "operator": "==", "value": value}]).json()
        assert [r["_row"] for r in body["rows"]] == [1]
    # a non-integral string on an int column still falls back to float
    body = _post(client, filters=[{"column": "x", "operator": ">", "value": "1.5"}]).json()
    assert body["filtered_rows"] == 2


@pytest.mark.parametrize("ascending", ["false", 0, None])
def test_sort_ascending_must_be_bool(
    store: ArtifactStore, client: TestClient, ascending: Any
) -> None:
    _put(store)
    resp = _post(client, sort=[{"column": "n", "ascending": ascending}])
    assert resp.status_code == 422 and "ascending" in resp.json()["error"]


def test_user_column_named_like_internal_row_is_preserved(
    store: ArtifactStore, client: TestClient
) -> None:
    _put(store, pd.DataFrame({"__ef_row__": [9, 8], "x": [1, 2]}))
    body = _post(client, sort=[{"column": "__ef_row__", "ascending": True}]).json()
    assert body["rows"] == [
        {"__ef_row__": 8, "x": 2, "_row": 1},
        {"__ef_row__": 9, "x": 1, "_row": 0},
    ]


def test_tz_mismatched_datetime_filters(store: ArtifactStore, client: TestClient) -> None:
    naive = pd.DataFrame({"t": pd.to_datetime(["2024-01-01", "2024-02-01"])})
    _put(store, naive)
    body = _post(
        client, filters=[{"column": "t", "operator": ">", "value": "2024-01-15T00:00:00+05:00"}]
    ).json()
    assert [r["_row"] for r in body["rows"]] == [1]
    aware = pd.DataFrame({"t": pd.to_datetime(["2024-01-01", "2024-02-01"]).tz_localize("UTC")})
    _put(store, aware)
    for value in ("2024-01-15T00:00:00-05:00", "2024-01-15"):
        body = _post(client, filters=[{"column": "t", "operator": ">", "value": value}]).json()
        assert [r["_row"] for r in body["rows"]] == [1]


def test_port_must_be_string(store: ArtifactStore, client: TestClient) -> None:
    _put(store)
    resp = _post(client, port=["frame"])
    assert resp.status_code == 422 and "'port' must be a string" in resp.json()["error"]
