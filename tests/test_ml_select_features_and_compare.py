"""
Golden + equivalence tests for the ``ml.select_features`` and ``ml.compare_models`` nodes.

Mirrors ``tests/test_ml_pipeline_and_selection.py``'s pattern, scoped to these two node types.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml import compare_models, select_features
from emergentflow.nodes.examples import CompareModels, LoadSample, SelectFeatures


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _classification_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = ["low" if i % 2 == 0 else "high" for i in range(40)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


# ---------------------------------------------------------------------------
# 1. Golden-code quality
# ---------------------------------------------------------------------------


def _build_select_features_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    sel = SelectFeatures().instantiate(
        selector="SelectKBest", target="target", params={"k": 2}, label="Select Features"
    )
    load_to_sel = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=sel.id, port_id=_in_port(sel, "frame").id),
    )
    return Graph(nodes={load.id: load, sel.id: sel}, edges={load_to_sel.id: load_to_sel})


def _build_compare_models_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    cmp_node = CompareModels().instantiate(
        task="classification",
        target="target",
        estimators=["LogisticRegression", "RandomForestClassifier"],
        cv=3,
        label="Compare Models",
    )
    load_to_cmp = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=cmp_node.id, port_id=_in_port(cmp_node, "frame").id),
    )
    return Graph(nodes={load.id: load, cmp_node.id: cmp_node}, edges={load_to_cmp.id: load_to_cmp})


_GOLDEN_GRAPH_BUILDERS = {
    "select_features": _build_select_features_graph,
    "compare_models": _build_compare_models_graph,
}


@pytest.mark.parametrize("name", sorted(_GOLDEN_GRAPH_BUILDERS))
def test_codegen_is_parseable(name: str) -> None:
    code = compile_to_code(_GOLDEN_GRAPH_BUILDERS[name]())
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("name", sorted(_GOLDEN_GRAPH_BUILDERS))
def test_codegen_is_ruff_clean(name: str) -> None:
    code = compile_to_code(_GOLDEN_GRAPH_BUILDERS[name]())
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_select_features_equivalence() -> None:
    """execute == running the emitted code, for ml.select_features."""
    df = _classification_df()

    defn = SelectFeatures()
    node = defn.instantiate(selector="SelectKBest", target="label", params={"k": 1})
    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_transformer = executed["transformer"]
    executed_result = executed["result"]
    executed_summary = executed["summary"]

    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_transformer = scope["transformer"]
    codegen_result = scope["result"]
    codegen_summary = scope["summary"]

    assert (
        executed_transformer.estimator_type == codegen_transformer.estimator_type == "SelectKBest"
    )
    assert executed_transformer.feature_names == codegen_transformer.feature_names
    pd.testing.assert_frame_equal(executed_result, codegen_result)
    pd.testing.assert_frame_equal(executed_summary, codegen_summary)


@pytest.mark.equivalence
def test_compare_models_equivalence() -> None:
    """execute == running the emitted code, for ml.compare_models."""
    df = _classification_df()

    defn = CompareModels()
    node = defn.instantiate(
        task="classification",
        target="label",
        estimators=["LogisticRegression", "RandomForestClassifier"],
        cv=3,
    )
    executed = defn.execute(node, inputs={"frame": df.copy()})
    executed_comparison = executed["comparison"]
    executed_model = executed["model"]

    scope = _run_codegen(defn, node, {"frame": df.copy()})
    codegen_comparison = scope["comparison"]
    codegen_model = scope["model"]

    # fit_time is wall-clock and expected to differ between the two runs; compare
    # every other column exactly.
    compare_cols = [c for c in executed_comparison.columns if c != "fit_time"]
    pd.testing.assert_frame_equal(
        executed_comparison[compare_cols], codegen_comparison[compare_cols]
    )
    assert executed_model.estimator_type == codegen_model.estimator_type
    assert executed_model.feature_names == codegen_model.feature_names
    assert (
        executed_model.estimator.predict(df[executed_model.feature_names]).tolist()
        == codegen_model.estimator.predict(df[codegen_model.feature_names]).tolist()
    )


# ---------------------------------------------------------------------------
# 3. estimator_ref mechanism + graceful-failure behavior
# ---------------------------------------------------------------------------


def test_select_features_rfe_uses_nested_estimator() -> None:
    """RFE's estimator_ref kwarg resolves to a real, fitted nested estimator instance."""
    df = _classification_df()
    transformer, _result, summary = select_features(
        df, selector="RFE", target="label", params={"n_features_to_select": 1}
    )
    assert type(transformer.transformer.estimator_).__name__ == "LogisticRegression"
    assert "ranking" in summary.columns


def test_select_features_select_from_model_uses_nested_estimator() -> None:
    """SelectFromModel's estimator_ref kwarg resolves to a real, fitted nested estimator."""
    df = _classification_df()
    transformer, _result, _summary = select_features(
        df, selector="SelectFromModel", target="label", params={}
    )
    assert type(transformer.transformer.estimator_).__name__ == "RandomForestClassifier"


def test_compare_models_handles_one_estimator_failing() -> None:
    """A curated estimator incompatible with this data (MultinomialNB needs non-negative
    features) degrades to a NaN row with a status message, instead of aborting the whole
    comparison."""
    df = pd.DataFrame(
        {
            "x1": [-1.0, -2.0, 1.0, 2.0, -1.5, 1.5, -2.5, 2.5],
            "y": [0, 0, 1, 1, 0, 1, 0, 1],
        }
    )
    comparison, best = compare_models(
        df,
        task="classification",
        target="y",
        estimators=["LogisticRegression", "MultinomialNB"],
        cv=2,
    )
    assert set(comparison["estimator"]) == {"LogisticRegression", "MultinomialNB"}
    failed_row = comparison[comparison["estimator"] == "MultinomialNB"].iloc[0]
    assert failed_row["status"] != "ok"
    assert pd.isna(failed_row["accuracy"])
    assert best.estimator_type == "LogisticRegression"
