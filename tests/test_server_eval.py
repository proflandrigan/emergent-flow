"""Tests for the Epic 9 Story 8 server glue: /eval/label, /export/eval_set, /export/finetune."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from emergentflow.server import app

_RESULTS = [
    {
        "row_id": 0,
        "input": {"q": "2+2?"},
        "messages": [{"role": "user", "content": "2+2?"}],
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "output": "4",
        "input_tokens": 5,
        "output_tokens": 1,
        "cost_usd": 0.0001,
        "latency_ms": 50.0,
        "finish_reason": "stop",
    },
]
_LABELS = [
    {"row_id": 0, "variant": "anthropic:claude-sonnet-5", "label": "pass", "score": 1.0},
]


def test_eval_label_route_merges() -> None:
    with TestClient(app) as test_client:
        resp = test_client.post("/eval/label", json={"results": _RESULTS, "labels": _LABELS})
    assert resp.status_code == 200
    labeled = resp.json()["labeled"]
    assert len(labeled) == 1
    assert labeled[0]["label"] == "pass"
    assert labeled[0]["score"] == 1.0


def test_eval_label_route_empty_labels() -> None:
    # An empty labels list builds a column-less DataFrame (`pd.DataFrame([])`), which
    # `emergentflow.eval.label.label` rejects (missing row_id/variant/label columns) via
    # `LabelColumnError` -- verified by running this, not assumed -- so the route surfaces
    # the project's normal 422 service-failure contract, not a 200 with 1 unlabeled row.
    with TestClient(app) as test_client:
        resp = test_client.post("/eval/label", json={"results": _RESULTS, "labels": []})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_export_eval_set_route_downloads_jsonl() -> None:
    with TestClient(app) as test_client:
        label_resp = test_client.post("/eval/label", json={"results": _RESULTS, "labels": _LABELS})
        assert label_resp.status_code == 200
        labeled_rows = label_resp.json()["labeled"]

        resp = test_client.post("/export/eval_set", json={"rows": labeled_rows})
    assert resp.status_code == 200
    assert "eval_set.jsonl" in resp.headers["content-disposition"]
    line = resp.content.decode("utf-8").strip()
    row = json.loads(line)
    assert row["input"] == _RESULTS[0]["input"]
    assert row["output"] == _RESULTS[0]["output"]
    assert row["label"] == "pass"


def test_export_finetune_route_downloads_jsonl() -> None:
    with TestClient(app) as test_client:
        label_resp = test_client.post("/eval/label", json={"results": _RESULTS, "labels": _LABELS})
        assert label_resp.status_code == 200
        labeled_rows = label_resp.json()["labeled"]

        resp = test_client.post("/export/finetune", json={"rows": labeled_rows})
    assert resp.status_code == 200
    assert "finetune.jsonl" in resp.headers["content-disposition"]
    line = resp.content.decode("utf-8").strip()
    row = json.loads(line)
    assert "messages" in row
    assert row["messages"][-1]["role"] == "assistant"


def test_export_eval_set_route_bad_json_body() -> None:
    with TestClient(app) as test_client:
        resp = test_client.post(
            "/export/eval_set", content=b"not json", headers={"Content-Type": "application/json"}
        )
    assert resp.status_code == 400
