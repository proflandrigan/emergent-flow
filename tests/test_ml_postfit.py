"""
Golden + equivalence tests for the post-fit model operations.

Covers ``calibrate_model``, ``optimize_threshold``, and ``finalize_model`` (Feature 4 of the
ml_feature_addons_1 plan). These all consume a ``FittedModel`` + a DataFrame and validate
that the node ``execute`` path and the compiled ``codegen`` path produce equivalent output
(ADR 0002). The produced estimator types (e.g. ``CalibratedClassifierCV``) are not in the
curated registry, so equivalence is keyed on raw predict/probability output rather than
``ef.ml.summarize``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.ml import (
    ThresholdResult,
    calibrate_model,
    finalize_model,
    fit_estimator,
    optimize_threshold,
)
from emergentflow.nodes.examples import (
    CalibrateModel,
    FinalizeModel,
    OptimizeThreshold,
)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _binary_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = [("low" if i % 2 == 0 else "high") for i in range(40)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def _regression_df() -> pd.DataFrame:
    x1 = [float(i) for i in range(30)]
    x2 = [float(i % 5) for i in range(30)]
    y = [2 * a + 3 * b + 1.0 for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


def _binary_classifier(df):
    return fit_estimator(df, estimator="LogisticRegression", target="label")


def _multi_class_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x1": range(30),
            "x2": range(30),
            "label": ["a", "b", "c"] * 10,
        }
    )


# ---------------------------------------------------------------------------
# calibrate_model
# ---------------------------------------------------------------------------


def test_calibrate_model_backend():
    df = _binary_df()
    base = _binary_classifier(df)
    c = calibrate_model(base, df, target="label", method="sigmoid")
    assert c.task == "classification"
    assert type(c.estimator).__name__ == "CalibratedClassifierCV"
    proba = c.estimator.predict_proba(df[["x1", "x2"]])
    assert proba.shape == (len(df), 2)


def test_calibrate_model_rejects_non_classification():
    df = _regression_df()
    base = fit_estimator(df, estimator="Ridge", target="y")
    with pytest.raises(ValueError):
        calibrate_model(base, df, target="y")


def test_calibrate_model_rejects_bad_method():
    df = _binary_df()
    base = _binary_classifier(df)
    with pytest.raises(ValueError):
        calibrate_model(base, df, target="label", method="bogus")


def test_calibrate_model_node_execute_and_codegen_equivalent():
    df = _binary_df()
    base = _binary_classifier(df)
    defn = CalibrateModel()
    node = defn.instantiate(target="label")
    execute_model = defn.execute(node, {"model": base, "frame": df.copy()})["model"]
    exec_proba = execute_model.estimator.predict_proba(df[["x1", "x2"]])
    scope = _run_codegen(defn, node, {"model": base, "frame": df.copy()})
    codegen_model = scope["model"]
    codegen_proba = codegen_model.estimator.predict_proba(df[["x1", "x2"]])
    assert list(exec_proba.shape) == list(codegen_proba.shape)
    assert (exec_proba[:, 1] == codegen_proba[:, 1]).all()


# ---------------------------------------------------------------------------
# optimize_threshold
# ---------------------------------------------------------------------------


def test_optimize_threshold_backend():
    df = _binary_df()
    base = _binary_classifier(df)
    r = optimize_threshold(base, df, target="label")
    assert isinstance(r, ThresholdResult)
    assert r.best_f1 > 0
    assert list(r.metrics.columns) == ["threshold", "precision", "recall", "f1"]
    assert 0.0 <= r.best_threshold <= 1.0
    assert r.positive_class == "low"


def test_optimize_threshold_respects_positive_class():
    df = _binary_df()
    base = _binary_classifier(df)
    r = optimize_threshold(base, df, target="label", positive_class="low")
    assert r.positive_class == "low"


def test_optimize_threshold_rejects_multi_class():
    df = _multi_class_df()
    base = fit_estimator(df, estimator="LogisticRegression", target="label")
    with pytest.raises(ValueError):
        optimize_threshold(base, df, target="label")


def test_optimize_threshold_rejects_non_classification():
    df = _regression_df()
    base = fit_estimator(df, estimator="Ridge", target="y")
    with pytest.raises(ValueError):
        optimize_threshold(base, df, target="y")


def test_optimize_threshold_node_execute_and_codegen_equivalent():
    df = _binary_df()
    base = _binary_classifier(df)
    defn = OptimizeThreshold()
    node = defn.instantiate(target="label")
    execute_result = defn.execute(node, {"model": base, "frame": df.copy()})["threshold_result"]
    scope = _run_codegen(defn, node, {"model": base, "frame": df.copy()})
    codegen_result = scope["threshold_result"]
    assert execute_result.best_threshold == codegen_result.best_threshold
    assert execute_result.metrics["f1"].tolist() == codegen_result.metrics["f1"].tolist()


# ---------------------------------------------------------------------------
# finalize_model
# ---------------------------------------------------------------------------


def test_finalize_model_backend_uses_model_target():
    df = _binary_df()
    base = _binary_classifier(df)
    f = finalize_model(base, df)
    assert f.task == "classification"
    assert f.target == "label"
    assert type(f.estimator).__name__ == "LogisticRegression"


def test_finalize_model_explicit_target():
    df = _binary_df()
    base = _binary_classifier(df)
    f = finalize_model(base, df, target="label")
    assert f.target == "label"


def test_finalize_model_requires_target():
    df = _binary_df()
    # a model with target=None (e.g. clustering) and no explicit target must raise
    cluster = fit_estimator(df.drop(columns=["label"]), estimator="KMeans")
    with pytest.raises(ValueError):
        finalize_model(cluster, df, target=None)


def test_finalize_model_node_execute_and_codegen_equivalent():
    df = _binary_df()
    base = _binary_classifier(df)
    defn = FinalizeModel()
    node = defn.instantiate()
    execute_model = defn.execute(node, {"model": base, "frame": df.copy()})["model"]
    exec_preds = execute_model.estimator.predict(df[["x1", "x2"]])
    scope = _run_codegen(defn, node, {"model": base, "frame": df.copy()})
    codegen_model = scope["model"]
    codegen_preds = codegen_model.estimator.predict(df[["x1", "x2"]])
    assert (exec_preds == codegen_preds).all()
