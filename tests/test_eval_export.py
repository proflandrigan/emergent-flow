"""Story 7's dataset export suite.

Schema-validated fixture tests for both export formats (`ef.export_eval_set` and
`ef.export_finetune`), a round-trip test per format, and a no-secret-fields test —
proving the exporters emit only the judged fields their schemas promise and never
leak provider/telemetry columns (e.g. `api_key_env`) present on the source DataFrame.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

from emergentflow.eval.export import DatasetExportManifest, export_eval_set, export_finetune


def _labeled_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "row_id": 0,
                "input": {"question": "2+2?"},
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "2+2?"},
                ],
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "output": "4",
                "input_tokens": 10,
                "output_tokens": 1,
                "cost_usd": 0.001,
                "latency_ms": 120.0,
                "finish_reason": "stop",
                "variant": "anthropic:claude-sonnet-5",
                "label": "pass",
                "score": 1.0,
                "rubric": "exact match",
                "note": None,
                "api_key_env": "ANTHROPIC_API_KEY",
            },
            {
                "row_id": 1,
                "input": {"question": "capital of France?"},
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "capital of France?"},
                ],
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "output": {"answer": "Paris"},
                "input_tokens": 12,
                "output_tokens": 3,
                "cost_usd": 0.0005,
                "latency_ms": 80.0,
                "finish_reason": "stop",
                "variant": "anthropic:claude-haiku-4-5-20251001",
                "label": "fail",
                "score": 0.0,
                "rubric": None,
                "note": "wrong format",
                "api_key_env": "ANTHROPIC_API_KEY",
            },
            {
                "row_id": 2,
                "input": {"question": "unlabeled row"},
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "unlabeled row"},
                ],
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "output": "unreviewed",
                "input_tokens": 5,
                "output_tokens": 1,
                "cost_usd": 0.0001,
                "latency_ms": 50.0,
                "finish_reason": "stop",
                "variant": "anthropic:claude-sonnet-5",
                "label": None,
                "score": None,
                "rubric": None,
                "note": None,
                "api_key_env": "ANTHROPIC_API_KEY",
            },
        ]
    )


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def test_export_eval_set_schema_and_skip_unlabeled(tmp_path: pathlib.Path) -> None:
    """export_eval_set skips unlabeled rows and omits null score/rubric keys."""
    df = _labeled_df()
    path = tmp_path / "eval_set.jsonl"
    export_eval_set(df, path)

    objs = _read_jsonl(path)
    assert len(objs) == 2

    by_question = {obj["input"]["question"]: obj for obj in objs}

    row0 = by_question["2+2?"]
    assert set(row0.keys()) == {"input", "output", "label", "score", "rubric"}
    assert row0["input"] == {"question": "2+2?"}
    assert row0["output"] == "4"
    assert row0["label"] == "pass"

    row1 = by_question["capital of France?"]
    assert set(row1.keys()) == {"input", "output", "label", "score"}
    assert row1["input"] == {"question": "capital of France?"}
    assert row1["output"] == {"answer": "Paris"}
    assert row1["label"] == "fail"


def test_export_eval_set_manifest(tmp_path: pathlib.Path) -> None:
    """The returned manifest's path/row_count/byte_size match the file on disk."""
    df = _labeled_df()
    path = tmp_path / "eval_set.jsonl"
    manifest: DatasetExportManifest = export_eval_set(df, path)

    assert manifest.row_count == 2
    assert manifest.path == path
    assert manifest.byte_size == path.stat().st_size


def test_export_eval_set_round_trip(tmp_path: pathlib.Path) -> None:
    """Reloaded rows match the source DataFrame's input/label per question."""
    df = _labeled_df()
    path = tmp_path / "eval_set.jsonl"
    manifest: DatasetExportManifest = export_eval_set(df, path)

    objs = _read_jsonl(path)
    assert len(objs) == manifest.row_count

    source_by_question = {row["input"]["question"]: row for row in df.to_dict(orient="records")}
    for obj in objs:
        source = source_by_question[obj["input"]["question"]]
        assert obj["input"] == source["input"]
        assert obj["label"] == source["label"]


def test_export_finetune_schema_and_skip_unlabeled(tmp_path: pathlib.Path) -> None:
    """export_finetune skips unlabeled rows and appends the assistant message."""
    df = _labeled_df()
    path = tmp_path / "finetune.jsonl"
    export_finetune(df, path)

    objs = _read_jsonl(path)
    assert len(objs) == 2

    for obj in objs:
        assert set(obj.keys()) == {"messages"}

    by_last_user = {obj["messages"][1]["content"]: obj for obj in objs}

    row0 = by_last_user["2+2?"]
    messages0 = row0["messages"]
    assert len(messages0) == 3
    assert messages0[0] == {"role": "system", "content": "You are terse."}
    assert messages0[1] == {"role": "user", "content": "2+2?"}
    assert messages0[2] == {"role": "assistant", "content": "4"}

    row1 = by_last_user["capital of France?"]
    messages1 = row1["messages"]
    assert len(messages1) == 3
    assert messages1[2]["role"] == "assistant"
    assert json.loads(messages1[2]["content"]) == {"answer": "Paris"}


def test_export_finetune_manifest(tmp_path: pathlib.Path) -> None:
    """The returned manifest's path/row_count/byte_size match the file on disk."""
    df = _labeled_df()
    path = tmp_path / "finetune.jsonl"
    manifest: DatasetExportManifest = export_finetune(df, path)

    assert manifest.row_count == 2
    assert manifest.path == path
    assert manifest.byte_size == path.stat().st_size


def test_export_finetune_round_trip(tmp_path: pathlib.Path) -> None:
    """Reloaded rows have one more message than the source, ending in assistant."""
    df = _labeled_df()
    path = tmp_path / "finetune.jsonl"
    manifest: DatasetExportManifest = export_finetune(df, path)

    objs = _read_jsonl(path)
    assert len(objs) == manifest.row_count

    source_rows = [row for row in df.to_dict(orient="records") if row["label"] is not None]
    source_by_last_user = {row["messages"][1]["content"]: row for row in source_rows}

    for obj in objs:
        last_user_content = obj["messages"][1]["content"]
        source = source_by_last_user[last_user_content]
        assert len(obj["messages"]) == len(source["messages"]) + 1
        assert obj["messages"][-1]["role"] == "assistant"


def test_exports_carry_no_secret_fields(tmp_path: pathlib.Path) -> None:
    """Neither export format carries the api_key_env probe or other telemetry fields."""
    df = _labeled_df()
    eval_path = tmp_path / "eval_set.jsonl"
    finetune_path = tmp_path / "finetune.jsonl"
    export_eval_set(df, eval_path)
    export_finetune(df, finetune_path)

    eval_text = eval_path.read_text(encoding="utf-8")
    finetune_text = finetune_path.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in eval_text
    assert "ANTHROPIC_API_KEY" not in finetune_text

    for obj in _read_jsonl(eval_path):
        assert "api_key_env" not in obj

    for obj in _read_jsonl(finetune_path):
        assert "api_key_env" not in obj
        for msg in obj["messages"]:
            assert "api_key_env" not in msg


def test_export_eval_set_rejects_non_dict_input(tmp_path: pathlib.Path) -> None:
    """A labeled row with a non-dict 'input' raises ValueError."""
    row = _labeled_df().iloc[0].to_dict()
    row["input"] = "not a dict"
    df = pd.DataFrame([row])

    with pytest.raises(ValueError):
        export_eval_set(df, tmp_path / "x.jsonl")


def test_export_finetune_rejects_empty_messages(tmp_path: pathlib.Path) -> None:
    """A labeled row with an empty 'messages' list raises ValueError."""
    row = _labeled_df().iloc[0].to_dict()
    row["messages"] = []
    df = pd.DataFrame([row])

    with pytest.raises(ValueError):
        export_finetune(df, tmp_path / "x.jsonl")
