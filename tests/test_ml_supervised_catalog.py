"""
Golden + equivalence tests for the Epic 8 Story 4 supervised estimator catalog.

Two things this file proves, per Story 4's own checklist and the Story 9 harness pattern:

1. Golden-code quality: for a representative estimator per family, the whole-graph
   ``compile_to_code`` output (LoadSample -> FitEstimator -> ApplyEstimator) is syntactically
   valid Python and passes ``ruff check`` -- readable, ruff-clean, importable generated code
   (mirrors ``tests/test_codegen_corpus_quality.py``'s idiom).
2. ADR-0002 equivalence at scale: for EVERY estimator registered with archetype="fit" (the
   entire supervised allow-list, computed dynamically so this test grows automatically as the
   allow-list widens), ``execute()`` and running the code ``codegen()`` emits produce the same
   fitted-model metadata and the same predictions.
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
from emergentflow.ml.registry import get_estimator_spec, known_estimator_keys
from emergentflow.nodes.examples import ApplyEstimator, FitEstimator, LoadSample


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _fit_archetype_keys() -> list[str]:
    return sorted(k for k in known_estimator_keys() if get_estimator_spec(k).archetype == "fit")


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


def _regression_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(30)]
    x2 = [float(i % 5) for i in range(30)]
    y = [2 * a + 3 * b + 1.0 for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative estimator per family.
# ---------------------------------------------------------------------------

_REPRESENTATIVE_ESTIMATORS = [
    "LogisticRegression",  # linear (seed)
    "Ridge",  # linear regressor
    "RandomForestClassifier",  # tree/ensemble classifier
    "GradientBoostingRegressor",  # tree/ensemble regressor
    "KNeighborsClassifier",  # neighbors
    "GaussianNB",  # naive bayes
    "SVC",  # svm
    "LinearDiscriminantAnalysis",  # discriminant analysis
]


def _build_fit_apply_graph(estimator_key: str) -> Graph:
    spec = get_estimator_spec(estimator_key)
    dataset = "iris" if spec.task == "classification" else "diabetes"
    load = LoadSample().instantiate(name=dataset, label="Load Sample")
    fit = FitEstimator().instantiate(estimator=estimator_key, target="target", label="Fit")
    apply_ = ApplyEstimator().instantiate(op="predict", label="Apply")

    load_to_fit = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    fit_to_apply_model = Edge(
        source=PortRef(node_id=fit.id, port_id=_out_port(fit, "model").id),
        target=PortRef(node_id=apply_.id, port_id=_in_port(apply_, "model").id),
    )
    load_to_apply_frame = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=apply_.id, port_id=_in_port(apply_, "frame").id),
    )
    return Graph(
        nodes={load.id: load, fit.id: fit, apply_.id: apply_},
        edges={
            load_to_fit.id: load_to_fit,
            fit_to_apply_model.id: fit_to_apply_model,
            load_to_apply_frame.id: load_to_apply_frame,
        },
    )


@pytest.mark.parametrize("estimator_key", _REPRESENTATIVE_ESTIMATORS)
def test_supervised_catalog_codegen_is_parseable(estimator_key: str) -> None:
    """Generated code for a representative supervised estimator parses (importable)."""
    code = compile_to_code(_build_fit_apply_graph(estimator_key))
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("estimator_key", _REPRESENTATIVE_ESTIMATORS)
def test_supervised_catalog_codegen_is_ruff_clean(estimator_key: str) -> None:
    """Generated code for a representative supervised estimator passes ``ruff check``."""
    code = compile_to_code(_build_fit_apply_graph(estimator_key))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence matrix: every "fit"-archetype estimator in the allow-list.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estimator_key", _fit_archetype_keys())
def test_fit_estimator_equivalence_matrix(estimator_key: str) -> None:
    """ADR 0002: execute == running the emitted code, for every fit-archetype estimator."""
    spec = get_estimator_spec(estimator_key)
    target = "label" if spec.task == "classification" else "y"
    df = _classification_df() if spec.task == "classification" else _regression_df()

    fit_defn = FitEstimator()
    fit_node = fit_defn.instantiate(estimator=estimator_key, target=target)
    executed_model = fit_defn.execute(fit_node, inputs={"frame": df.copy()})["model"]
    scope = _run_codegen(fit_defn, fit_node, {"frame": df.copy()})
    codegen_model = scope["model"]

    assert executed_model.estimator_type == codegen_model.estimator_type
    assert executed_model.task == codegen_model.task
    assert executed_model.target == codegen_model.target
    assert executed_model.feature_names == codegen_model.feature_names
    assert (
        executed_model.estimator.predict(df[executed_model.feature_names]).tolist()
        == codegen_model.estimator.predict(df[codegen_model.feature_names]).tolist()
    )

    apply_defn = ApplyEstimator()
    apply_node = apply_defn.instantiate(op="predict")
    executed_result = apply_defn.execute(
        apply_node, inputs={"model": executed_model, "frame": df.copy()}
    )["result"]
    apply_scope = _run_codegen(apply_defn, apply_node, {"model": codegen_model, "frame": df.copy()})
    assert executed_result["prediction"].tolist() == apply_scope["result"]["prediction"].tolist()
