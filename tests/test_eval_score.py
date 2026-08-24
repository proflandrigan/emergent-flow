"""
tests/test_eval_score.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for ``emergentflow.eval.score.score``,
``emergentflow.eval.score.summarize_scores``, and the ``eval.score`` node
(issue #93 part 2).
"""

from __future__ import annotations

import pandas as pd
import pytest

import emergentflow as ef
from emergentflow.eval.score import ScorerError, score, summarize_scores
from emergentflow.ir import Direction, Edge, Graph, Node, Param, Port, PortRef
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.examples.eval_score import EvalScore
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import ParamSpec, PortSpec

# ---------------------------------------------------------------------------
# Fixture DataFrames
# ---------------------------------------------------------------------------


def _two_row_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "output": ["hello world", "goodbye world"],
            "expected": ["hello world", "hello world"],
        }
    )


def _contains_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "output": ["hello world and more", "nothing here"],
        }
    )


def _regex_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "output": ["abc-123-def", "no-digits"],
        }
    )


def _numeric_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "output": [5.0, 5.0],
            "expected": [5.0, 10.0],
        }
    )


def _json_schema_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "output": ['{"x": 1}', '{"y": 2}', "not-json"],
        }
    )


def _score_results_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [0, 0, 1, 1],
            "input": [{"q": "a"}, {"q": "a"}, {"q": "b"}, {"q": "b"}],
            "provider": ["anthropic", "openai", "anthropic", "openai"],
            "model": ["claude-sonnet-5", "gpt-4o", "claude-sonnet-5", "gpt-4o"],
            "output": ["hello world", "goodbye world", "hello world", "goodbye world"],
        }
    )


# ---------------------------------------------------------------------------
# 1-6: score() unit tests
# ---------------------------------------------------------------------------


def test_score_exact_match():
    df = _two_row_df()
    result = score(df, [{"name": "exact", "kind": "exact_match", "reference_column": "expected"}])
    assert list(result["score_exact"]) == [1.0, 0.0]


def test_score_exact_match_case_insensitive():
    df = pd.DataFrame(
        {
            "output": ["HELLO World", "goodbye"],
            "expected": ["hello world", "hello world"],
        }
    )
    result = score(
        df,
        [
            {
                "name": "exact",
                "kind": "exact_match",
                "reference_column": "expected",
                "case_sensitive": False,
            }
        ],
    )
    assert list(result["score_exact"]) == [1.0, 0.0]


def test_score_contains():
    df = _contains_df()
    result = score(df, [{"name": "has_hello", "kind": "contains", "substring": "hello"}])
    assert list(result["score_has_hello"]) == [1.0, 0.0]


def test_score_contains_case_insensitive():
    df = _contains_df()
    result = score(
        df,
        [
            {
                "name": "has_hello",
                "kind": "contains",
                "substring": "HELLO",
                "case_sensitive": False,
            }
        ],
    )
    assert list(result["score_has_hello"]) == [1.0, 0.0]


def test_score_regex():
    df = _regex_df()
    result = score(df, [{"name": "has_digits", "kind": "regex", "pattern": r"\d+"}])
    assert list(result["score_has_digits"]) == [1.0, 0.0]


def test_score_numeric_distance_within_tolerance():
    df = _numeric_df()
    result = score(
        df,
        [
            {
                "name": "close",
                "kind": "numeric_distance",
                "reference_column": "expected",
                "max_distance": 2.0,
            }
        ],
    )
    assert list(result["score_close"]) == [1.0, 0.0]


def test_score_numeric_distance_non_numeric_returns_zero():
    df = pd.DataFrame(
        {
            "output": ["not-a-number", "5"],
            "expected": [1.0, 10.0],
        }
    )
    result = score(
        df,
        [
            {
                "name": "close",
                "kind": "numeric_distance",
                "reference_column": "expected",
                "max_distance": 1.0,
            }
        ],
    )
    assert list(result["score_close"]) == [0.0, 0.0]


def test_score_json_schema_valid():
    df = _json_schema_df()
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
    result = score(df, [{"name": "has_x", "kind": "json_schema", "schema": schema}])
    assert list(result["score_has_x"]) == [1.0, 0.0, 0.0]


def test_score_json_schema_accepts_integral_float_and_numpy_scalar():
    # JSON `"3.0"` parses to the float 3.0; JSON Schema's `integer` type is a number
    # with a zero fractional part, so it must score as a match rather than a type
    # violation. Numpy ints/real floats (common from pandas rows) are not
    # isinstance-subclasses of python int/float and must also pass.
    import numpy as np

    from emergentflow.eval.score import _score_json_schema

    df = pd.DataFrame({"output": ['{"x": 3.0}', '{"x": 3.5}', np.nan, '{"x": 3}']})
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
    result = score(df, [{"name": "int_ok", "kind": "json_schema", "schema": schema}])
    assert list(result["score_int_ok"]) == [1.0, 0.0, 0.0, 1.0]

    for value, expect in [(np.int64(3), 1.0), (np.float64(3.5), 0.0), (np.float64(3.0), 1.0)]:
        assert _score_json_schema(value, {"schema": {"type": "integer"}}, None) == expect

    for value, expect in [
        (np.int64(3), 1.0),
        (np.float64(3.5), 1.0),
        (True, 0.0),
    ]:
        assert _score_json_schema(value, {"schema": {"type": "number"}}, None) == expect


def test_score_json_schema_on_native_dict():
    df = pd.DataFrame(
        {
            "output": [{"x": 1}, {"y": 2}],
        }
    )
    schema = {"type": "object", "required": ["x"]}
    result = score(df, [{"name": "has_x", "kind": "json_schema", "schema": schema}])
    assert list(result["score_has_x"]) == [1.0, 0.0]


def test_score_missing_name_raises():
    df = _two_row_df()
    with pytest.raises(ScorerError, match="missing 'name' or 'kind'"):
        score(df, [{"kind": "exact_match", "reference_column": "expected"}])


def test_score_missing_kind_raises():
    df = _two_row_df()
    with pytest.raises(ScorerError, match="missing 'name' or 'kind'"):
        score(df, [{"name": "x"}])


def test_score_unknown_kind_raises():
    df = _two_row_df()
    with pytest.raises(ScorerError, match="unknown scorer kind"):
        score(df, [{"name": "x", "kind": "magic"}])


# ---------------------------------------------------------------------------
# 7-8: summarize_scores() unit tests
# ---------------------------------------------------------------------------


def test_summarize_scores_one_variant():
    df = pd.DataFrame(
        {
            "provider": ["anthropic", "anthropic"],
            "model": ["claude-sonnet-5", "claude-sonnet-5"],
            "output": ["hello", "world"],
            "score_x": [1.0, 0.0],
        }
    )
    result = summarize_scores(df)
    assert list(result["variant"]) == ["anthropic:claude-sonnet-5"]
    assert list(result["n"]) == [2]
    assert list(result["mean_x"]) == [0.5]


def test_summarize_scores_two_variants():
    df = _score_results_df()
    df["score_x"] = [1.0, 1.0, 0.0, 0.0]
    result = summarize_scores(df)
    assert set(result["variant"]) == {"anthropic:claude-sonnet-5", "openai:gpt-4o"}
    assert list(result["n"]) == [2, 2]
    assert list(result["mean_x"]) == [0.5, 0.5]


def test_summarize_scores_multiple_score_columns():
    df = _score_results_df()
    df["score_exact"] = [1.0, 0.0, 1.0, 0.0]
    df["score_has_greeting"] = [1.0, 0.0, 1.0, 0.0]
    result = summarize_scores(df)
    assert "mean_exact" in result.columns
    assert "mean_has_greeting" in result.columns
    assert result.shape[0] == 2


def test_summarize_scores_no_score_column_raises():
    df = _score_results_df()
    with pytest.raises(ValueError, match="no score_\\* column"):
        summarize_scores(df)


# ---------------------------------------------------------------------------
# 9: EvalScore node via .instantiate()
# ---------------------------------------------------------------------------


def test_eval_score_node_execute():
    node = EvalScore().instantiate(
        scorers=[
            {"name": "exact", "kind": "exact_match", "reference_column": "expected"},
        ]
    )
    inputs_df = pd.DataFrame(
        {
            "row_id": [0, 1],
            "provider": ["anthropic", "anthropic"],
            "model": ["claude-sonnet-5", "claude-sonnet-5"],
            "output": ["hello world", "goodbye world"],
            "expected": ["hello world", "hello world"],
        }
    )
    out = EvalScore().execute(node, {"results": inputs_df})
    assert "scored" in out
    assert "metrics" in out
    assert list(out["scored"]["score_exact"]) == [1.0, 0.0]
    assert out["scored"].shape == (2, 6)
    assert out["metrics"].shape[0] == 1


def test_eval_score_node_preview():
    node = EvalScore().instantiate(
        scorers=[
            {"name": "exact", "kind": "exact_match", "reference_column": "expected"},
        ]
    )
    frag = EvalScore().preview(node)
    assert "ef.eval.score(" in frag.body
    assert "ef.eval.summarize_scores(" in frag.body


# ---------------------------------------------------------------------------
# 10: ADR-0002 equivalence test
# ---------------------------------------------------------------------------


@register
class _TestScoreSource(NodeDefinition):
    """Test fixture: 0 in, 1 out, produces a DataFrame for eval score tests."""

    type = "test.score_source"
    family = "test"
    label = "ScoreSrc"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="DataFrame")]
    params = [ParamSpec(name="data", type_token="dict", default={})]

    def codegen(self, node, ctx) -> CodeFragment:
        val = next(p.value for p in node.params if p.name == "data")
        return CodeFragment(
            imports=["import pandas as pd"],
            body=f"{ctx.out_var('out')} = pd.DataFrame({val!r})",
        )

    def execute(self, node, inputs: dict) -> dict:
        val = next(p.value for p in node.params if p.name == "data")
        return {"out": pd.DataFrame(val)}


def test_adr_0002_equivalence():
    data = {
        "row_id": [0, 1],
        "input": [{"q": "a"}, {"q": "b"}],
        "provider": ["anthropic", "anthropic"],
        "model": ["claude-sonnet-5", "claude-sonnet-5"],
        "output": ["hello world", "bad"],
        "expected": ["hello world", "hello world"],
    }

    source = Node(
        id="src",
        type=_TestScoreSource.type,
        label=_TestScoreSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="DataFrame")],
        params=[Param(name="data", type_token="dict", value=data)],
    )
    score_node = EvalScore().instantiate(
        scorers=[
            {"name": "exact", "kind": "exact_match", "reference_column": "expected"},
            {"name": "has_hello", "kind": "contains", "substring": "hello"},
        ]
    )

    src_out = next(p for p in source.ports if p.direction == Direction.OUT)
    score_in = next(p for p in score_node.ports if p.direction == Direction.IN)
    edge = Edge(
        source=PortRef(node_id=source.id, port_id=src_out.id),
        target=PortRef(node_id=score_node.id, port_id=score_in.id),
    )
    graph = Graph(
        nodes={source.id: source, score_node.id: score_node},
        edges={edge.id: edge},
    )

    exec_results = ef.execute(graph)
    exec_scored = exec_results[score_node.id]["scored"]
    exec_metrics = exec_results[score_node.id]["metrics"]

    source_code = ef.compile_to_code(graph)
    scope: dict = {}
    exec(source_code, scope)  # noqa: S102 -- test-only, trusted source
    compiled_results = scope["main"]()
    compiled_scored = compiled_results["eval_score_scored"]
    compiled_metrics = compiled_results["eval_score_metrics"]

    pd.testing.assert_frame_equal(exec_scored, compiled_scored)
    pd.testing.assert_frame_equal(exec_metrics, compiled_metrics)
