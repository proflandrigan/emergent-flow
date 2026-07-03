"""
tests/test_eval_label.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for `emergentflow.eval.label.label()` (join/merge, partial labels,
missing-column and duplicate-pair errors, no-mutation-of-inputs) plus a
golden + ADR-0002 equivalence test for the `eval.label` node (Epic 9 Story 6).
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.eval import LabelColumnError, label
from emergentflow.nodes.examples.eval_label import EvalLabel


def _results_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [0, 0, 1, 1],
            "input": [{"q": "a"}, {"q": "a"}, {"q": "b"}, {"q": "b"}],
            "provider": ["anthropic", "anthropic", "anthropic", "anthropic"],
            "model": ["claude-sonnet-5", "claude-haiku-4-5-20251001"] * 2,
            "output": ["out-0-sonnet", "out-0-haiku", "out-1-sonnet", "out-1-haiku"],
        }
    )


def _full_labels_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [0, 0, 1, 1],
            "variant": [
                "anthropic:claude-sonnet-5",
                "anthropic:claude-haiku-4-5-20251001",
                "anthropic:claude-sonnet-5",
                "anthropic:claude-haiku-4-5-20251001",
            ],
            "label": ["good", "bad", "bad", "good"],
            "score": [1.0, 0.0, 0.0, 1.0],
            "rubric": ["r0", "r1", "r2", "r3"],
            "note": ["n0", "n1", "n2", "n3"],
        }
    )


def test_label_merges_full_labels():
    results_df = _results_df()
    labels_df = _full_labels_df()

    result = label(results_df, labels_df)

    assert len(result) == 4
    assert list(result.columns) == [
        "row_id",
        "input",
        "provider",
        "model",
        "output",
        "variant",
        "label",
        "score",
        "rubric",
        "note",
    ]

    expected = {
        (0, "anthropic:claude-sonnet-5"): ("good", 1.0, "r0", "n0"),
        (0, "anthropic:claude-haiku-4-5-20251001"): ("bad", 0.0, "r1", "n1"),
        (1, "anthropic:claude-sonnet-5"): ("bad", 0.0, "r2", "n2"),
        (1, "anthropic:claude-haiku-4-5-20251001"): ("good", 1.0, "r3", "n3"),
    }
    for _, row in result.iterrows():
        key = (row["row_id"], row["variant"])
        assert (row["label"], row["score"], row["rubric"], row["note"]) == expected[key]


def test_label_partial_labels_are_nan():
    results_df = _results_df()
    labels_df = pd.DataFrame(
        {
            "row_id": [0],
            "variant": ["anthropic:claude-sonnet-5"],
            "label": ["good"],
        }
    )

    result = label(results_df, labels_df)

    assert len(result) == 4
    assert list(result.columns[-5:]) == ["variant", "label", "score", "rubric", "note"]

    non_null_label_rows = result[result["label"].notna()]
    assert len(non_null_label_rows) == 1
    assert non_null_label_rows.iloc[0]["label"] == "good"

    null_rows = result[result["label"].isna()]
    assert len(null_rows) == 3
    for _, row in null_rows.iterrows():
        assert pd.isna(row["label"])
        assert pd.isna(row["score"])
        assert pd.isna(row["rubric"])
        assert pd.isna(row["note"])


def test_label_missing_required_column_raises():
    results_df = _results_df()
    labels_df = pd.DataFrame(
        {
            "row_id": [0],
            "variant": ["anthropic:claude-sonnet-5"],
        }
    )

    with pytest.raises(LabelColumnError):
        label(results_df, labels_df)


def test_label_duplicate_pair_raises():
    results_df = _results_df()
    labels_df = pd.DataFrame(
        {
            "row_id": [0, 0],
            "variant": ["anthropic:claude-sonnet-5", "anthropic:claude-sonnet-5"],
            "label": ["good", "bad"],
        }
    )

    with pytest.raises(LabelColumnError):
        label(results_df, labels_df)


def test_label_does_not_mutate_inputs():
    results_df = _results_df()
    labels_df = _full_labels_df()

    label(results_df, labels_df)

    assert "variant" not in results_df.columns
    assert "label" not in results_df.columns


def test_label_result_is_inspectable():
    results_df = _results_df()
    labels_df = _full_labels_df()

    assert is_inspectable(label(results_df, labels_df))


def test_eval_label_golden_preview_code():
    """The node's codegen preview is deterministic, readable ef.eval.label(...) source."""
    node = EvalLabel().instantiate()
    frag = EvalLabel().preview(node)

    assert "ef.eval.label(" in frag.body
    assert EvalLabel().preview(node).body == frag.body


def test_eval_label_node_equivalence():
    """execute() and the codegen preview (exec'd) produce an identical labeled table."""
    node = EvalLabel().instantiate()
    results_df = _results_df()
    labels_df = _full_labels_df()

    frag = EvalLabel().preview(node)
    scope = {"results": results_df, "labels": labels_df}
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    codegen_result = scope["labeled"]

    exec_result = EvalLabel().execute(node, {"results": results_df, "labels": labels_df})["labeled"]

    pd.testing.assert_frame_equal(codegen_result, exec_result)
    assert exec_result.shape == (4, 10)
    assert exec_result["label"].notna().all()
