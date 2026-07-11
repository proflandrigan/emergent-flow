"""
emergentflow.explain
~~~~~~~~~~~~~~~~~~~~~
Model explainability: SHAP-based feature attribution and error analysis over an already-fitted
``ml.FittedModel`` (ADR 0020). A pure, in-process reader — no new injected-client seam, no new
IR types. Requires the optional ``emergentflow[explain]`` dependency group (shap) for any
SHAP-backed operation; error-analysis/diagnostic operations need no extra dependency beyond the
SDK's existing hard deps (pandas, scikit-learn, plotly).

See ``docs/adr/0020-model-explainability-family.md``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from emergentflow.api import public_op
from emergentflow.explain._shap import build_explanation, to_tidy_frame
from emergentflow.explain.errors import UnsupportedModelError
from emergentflow.ml import FittedModel
from emergentflow.viz.models import PlotSpec

__all__ = [
    "error_table",
    "plot_calibration",
    "plot_predicted_vs_actual",
    "plot_residuals",
    "plot_roc_pr",
    "plot_shap_beeswarm",
    "plot_shap_importance",
    "plot_shap_waterfall",
    "shap_values",
]


@public_op(name="ef.explain.shap_values")
def shap_values(
    model: FittedModel, frame: pd.DataFrame, *, seed: int, background_samples: int = 100
) -> pd.DataFrame:
    """Compute per-feature SHAP attributions for *model* over *frame*, as a tidy DataFrame.

    Requires a supervised ``fit``-archetype :class:`~emergentflow.ml.FittedModel` (raises
    :class:`~emergentflow.explain.errors.UnsupportedModelError` for a clustering model or a
    fitted transformer). Requires the optional ``emergentflow[explain]`` dependency group
    (raises :class:`~emergentflow.explain.errors.MissingOptionalDependencyError` if ``shap`` is
    not installed).

    Uses ``shap.TreeExplainer`` (exact, deterministic, no sampling) for pure tree-ensemble
    regressors; every other model (every classifier, every non-tree regressor) uses a seeded,
    background-sampled ``shap.Explainer`` (``PermutationExplainer``) -- see
    ``docs/adr/0020-model-explainability-family.md`` Decision clause 3 for why classification
    never uses ``TreeExplainer``. ``background_samples`` bounds and ``seed`` fixes the background
    sample drawn from *frame* wherever sampling is used; deterministic given the same inputs.

    Returns a tidy, long-format DataFrame with one row per ``(row_index, feature[, class])``:
    ``row_index`` (0-indexed position in *frame*), ``feature``, ``feature_value``, ``shap_value``,
    ``base_value``, and -- only for a multiclass classifier -- ``class``. Binary classification
    explains only the positive class's probability (mirrors ``ef.ml.evaluate``'s
    ``pos_label = classes[1]`` convention); regression and binary classification have no ``class``
    column. Never mutates *frame*.
    """
    explanation = build_explanation(model, frame, seed=seed, background_samples=background_samples)
    return to_tidy_frame(explanation, model, frame)


@public_op(name="ef.explain.plot_shap_importance")
def plot_shap_importance(shap_values: pd.DataFrame) -> PlotSpec:
    """Build a ranked bar chart of mean |SHAP value| per feature from a tidy shap_values frame.

    Consumes the tidy, long-format DataFrame ``ef.explain.shap_values`` produces (ADR 0020,
    Decision clause 4): one row per ``(row_index, feature[, class])``. For a multiclass frame (a
    ``class`` column present), renders one grouped horizontal bar per feature per class, colored
    by class, with every class's bars ordered by the SAME overall feature ranking (mean |SHAP
    value| across all classes) so features line up across class groups. For a single-output frame
    (regression or binary classification), renders one bar per feature. Features are sorted
    ascending by mean |SHAP value| so the largest-magnitude feature renders at the top of the
    horizontal bar chart (plotly's default bottom-to-top category ordering for a horizontal bar).
    """
    import plotly.graph_objects as go

    df = shap_values.copy()
    df["abs_shap"] = df["shap_value"].abs()

    fig = go.Figure()
    if "class" in df.columns:
        overall_order = (
            df.groupby("feature")["abs_shap"].mean().sort_values(ascending=True).index.tolist()
        )
        for cls in sorted(df["class"].unique(), key=str):
            per_feature = (
                df[df["class"] == cls].groupby("feature")["abs_shap"].mean().reindex(overall_order)
            )
            fig.add_bar(
                x=per_feature.tolist(),
                y=per_feature.index.tolist(),
                name=str(cls),
                orientation="h",
            )
        fig.update_layout(barmode="group")
    else:
        per_feature = df.groupby("feature")["abs_shap"].mean().sort_values(ascending=True)
        fig.add_bar(x=per_feature.tolist(), y=per_feature.index.tolist(), orientation="h")

    fig.update_layout(
        title="SHAP Feature Importance",
        xaxis_title="mean(|SHAP value|)",
        yaxis_title="Feature",
    )
    return PlotSpec.from_figure("shap_importance", fig)


@public_op(name="ef.explain.plot_shap_beeswarm")
def plot_shap_beeswarm(shap_values: pd.DataFrame) -> PlotSpec:
    """Build a jittered strip plot (a JSON-native approximation of SHAP's beeswarm summary plot)
    from a tidy shap_values frame.

    Consumes the tidy, long-format DataFrame ``ef.explain.shap_values`` produces (ADR 0020,
    Decision clause 4). One marker per ``(row_index, feature)``: x is ``shap_value``, y is the
    feature's row (features ordered by mean |SHAP value| ascending, same convention as
    :func:`plot_shap_importance`), y-jittered by a small, DETERMINISTIC, evenly-spaced offset
    (never randomized -- a second source of randomness here would break the ADR-0002 equivalence
    gate independently of ``shap_values``'s own ``seed`` param), and colored by that row's
    ``feature_value`` min-max normalized WITHIN its own feature's group (a non-numeric or
    constant-valued feature group falls back to a constant mid-scale color rather than raising).

    Only supports a single-output frame (regression or binary classification, no ``class``
    column); raises ``ValueError`` for a multiclass frame -- filter to one class first.
    """
    import plotly.graph_objects as go

    if "class" in shap_values.columns:
        raise ValueError(
            "plot_shap_beeswarm does not support a multiclass shap_values frame (a 'class' "
            "column is present); filter to one class's rows first."
        )

    df = shap_values.copy()
    df["abs_shap"] = df["shap_value"].abs()
    feature_order = (
        df.groupby("feature")["abs_shap"].mean().sort_values(ascending=True).index.tolist()
    )
    y_base = {feat: i for i, feat in enumerate(feature_order)}

    xs: list[float] = []
    ys: list[float] = []
    colors: list[float] = []
    for feat in feature_order:
        group = df[df["feature"] == feat].reset_index(drop=True)
        n = len(group)
        jitter = np.linspace(-0.4, 0.4, n) if n > 1 else np.array([0.0])
        numeric_vals = pd.to_numeric(group["feature_value"], errors="coerce")
        vmin, vmax = numeric_vals.min(), numeric_vals.max()
        if pd.isna(vmin) or pd.isna(vmax) or vmin == vmax:
            normalized = pd.Series(0.5, index=group.index)
        else:
            normalized = (numeric_vals - vmin) / (vmax - vmin)
        xs.extend(group["shap_value"].tolist())
        ys.extend((y_base[feat] + jitter).tolist())
        colors.extend(normalized.fillna(0.5).tolist())

    fig = go.Figure(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker={
                "color": colors,
                "colorscale": "Bluered",
                "showscale": True,
                "colorbar": {"title": "Feature value (normalized)"},
                "size": 6,
            },
        )
    )
    fig.update_layout(
        title="SHAP Summary (Beeswarm)",
        xaxis_title="SHAP value",
        yaxis={
            "tickvals": list(range(len(feature_order))),
            "ticktext": feature_order,
            "title": "Feature",
        },
    )
    return PlotSpec.from_figure("shap_beeswarm", fig)


@public_op(name="ef.explain.plot_shap_waterfall")
def plot_shap_waterfall(shap_values: pd.DataFrame, *, row_index: int) -> PlotSpec:
    """Build a waterfall chart explaining ONE row's prediction, from a tidy shap_values frame.

    Consumes the tidy, long-format DataFrame ``ef.explain.shap_values`` produces (ADR 0020,
    Decision clause 4). Starts at the row's ``base_value`` (the model's average/expected
    prediction), adds one bar per feature (that row's ``shap_value``, sorted by descending
    |shap_value| so the most influential features anchor the chart first), and ends at the row's
    final prediction (``base_value + sum(shap_value)``). Uses plotly's native ``go.Waterfall``
    chart type.

    Only supports a single-output frame (regression or binary classification, no ``class``
    column); raises ``ValueError`` for a multiclass frame -- filter to one class first. Raises
    ``ValueError`` if ``row_index`` is not present in *shap_values*.
    """
    import plotly.graph_objects as go

    if "class" in shap_values.columns:
        raise ValueError(
            "plot_shap_waterfall does not support a multiclass shap_values frame (a 'class' "
            "column is present); filter to one class's rows first."
        )

    row_df = shap_values[shap_values["row_index"] == row_index]
    if row_df.empty:
        raise ValueError(f"row_index {row_index!r} not found in the shap_values frame.")

    row_df = row_df.assign(_abs_shap=row_df["shap_value"].abs()).sort_values(
        "_abs_shap", ascending=False, kind="stable"
    )
    base_value = float(row_df["base_value"].iloc[0])
    features = row_df["feature"].tolist()
    shap_deltas = [float(v) for v in row_df["shap_value"]]
    prediction = base_value + sum(shap_deltas)

    fig = go.Figure(
        go.Waterfall(
            x=["base value", *features, "prediction"],
            y=[base_value, *shap_deltas, prediction],
            measure=["absolute", *(["relative"] * len(features)), "total"],
            connector={"line": {"color": "rgba(63, 63, 63, 0.5)"}},
        )
    )
    fig.update_layout(
        title=f"SHAP Waterfall (row {row_index})",
        yaxis_title="Model output",
    )
    return PlotSpec.from_figure("shap_waterfall", fig)


@public_op(name="ef.explain.error_table")
def error_table(model: FittedModel, frame: pd.DataFrame, *, top_n: int = 20) -> pd.DataFrame:
    """Return the *top_n* worst-error rows for a fitted, supervised model scored against *frame*.

    Requires a supervised ``fit``-archetype :class:`~emergentflow.ml.FittedModel` (raises
    :class:`~emergentflow.explain.errors.UnsupportedModelError` for a clustering model or a
    fitted transformer) and that *frame* has both ``model.target`` and every one of
    ``model.feature_names``.

    Regression: ranks rows by descending ``abs_error`` (``|residual|``, where
    ``residual = actual - prediction``, matching this codebase's existing statsmodels-residual
    convention). Columns: ``row_index``, ``model.target``, ``prediction``, ``residual``,
    ``abs_error``.

    Classification: requires ``predict_proba`` (raises ``UnsupportedModelError`` otherwise, same
    restriction ``ef.explain.shap_values`` already applies to classification). Ranks rows with
    misclassified predictions FIRST, then by ascending ``confidence`` (the predicted class's own
    probability) within each group -- so the least-confident wrong predictions rank worst.
    ``prediction`` and ``confidence`` are BOTH derived from the same ``predict_proba`` call's
    ``argmax`` (rather than calling ``.predict()`` separately), so they are guaranteed to agree by
    construction even for an estimator with a non-default decision threshold. Columns:
    ``row_index``, ``model.target``, ``prediction``, ``correct``, ``confidence``. Works for both
    binary and multiclass classification (unlike the SHAP plot nodes, this needs no
    single-output/multiclass split -- it deals in labels and probabilities directly, not
    per-feature attributions).

    Never mutates *frame*. Deterministic: no sampling, no randomness anywhere in this function.
    """
    if not isinstance(model, FittedModel) or model.target is None:
        raise UnsupportedModelError(
            "error_table requires a supervised FittedModel (ml.fit_estimator's 'fit' archetype); "
            "clustering models and fitted transformers are not supported."
        )
    if model.target not in frame.columns:
        raise ValueError(f"missing target column {model.target!r}.")
    missing = [c for c in model.feature_names if c not in frame.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")

    X = frame[model.feature_names]
    y_true = frame[model.target].to_numpy()
    row_index = np.arange(len(frame))

    if model.task == "regression":
        y_pred = model.estimator.predict(X)
        residual = y_true - y_pred
        result = pd.DataFrame(
            {
                "row_index": row_index,
                model.target: y_true,
                "prediction": y_pred,
                "residual": residual,
                "abs_error": np.abs(residual),
            }
        )
        return (
            result.sort_values("abs_error", ascending=False, kind="stable")
            .head(top_n)
            .reset_index(drop=True)
        )

    if model.task == "classification":
        if not hasattr(model.estimator, "predict_proba"):
            raise UnsupportedModelError(
                f"{model.estimator_type} has no predict_proba; classification error tables "
                "require a probability-capable estimator."
            )
        proba = model.estimator.predict_proba(X)
        classes = list(model.estimator.classes_)
        pred_idx = proba.argmax(axis=1)
        y_pred = np.asarray([classes[i] for i in pred_idx])
        confidence = proba[np.arange(len(proba)), pred_idx]
        correct = y_true == y_pred
        result = pd.DataFrame(
            {
                "row_index": row_index,
                model.target: y_true,
                "prediction": y_pred,
                "correct": correct,
                "confidence": confidence,
            }
        )
        return (
            result.sort_values(["correct", "confidence"], ascending=[True, True], kind="stable")
            .head(top_n)
            .reset_index(drop=True)
        )

    raise UnsupportedModelError(
        f"error_table requires a classification or regression model; got task={model.task!r}."
    )


def _require_regression_model(
    model: FittedModel, frame: pd.DataFrame
) -> tuple[pd.DataFrame, np.ndarray]:
    """Validate *model* is a fitted, supervised REGRESSION model with all its feature columns and
    target present in *frame*; return ``(X, y_true)``.

    Shared by :func:`plot_predicted_vs_actual` and :func:`plot_residuals` -- both regression-only
    diagnostic plots. Raises :class:`~emergentflow.explain.errors.UnsupportedModelError` for a
    non-regression model (classification, clustering, or a fitted transformer).
    """
    if not isinstance(model, FittedModel) or model.target is None:
        raise UnsupportedModelError(
            "this plot requires a supervised FittedModel (ml.fit_estimator's 'fit' archetype); "
            "clustering models and fitted transformers are not supported."
        )
    if model.task != "regression":
        raise UnsupportedModelError(
            f"this plot requires a regression model; got task={model.task!r}."
        )
    if model.target not in frame.columns:
        raise ValueError(f"missing target column {model.target!r}.")
    missing = [c for c in model.feature_names if c not in frame.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")
    X = frame[model.feature_names]
    y_true = frame[model.target].to_numpy()
    return X, y_true


@public_op(name="ef.explain.plot_predicted_vs_actual")
def plot_predicted_vs_actual(model: FittedModel, frame: pd.DataFrame) -> PlotSpec:
    """Scatter of actual vs. predicted values for a fitted regression model, with a y=x reference
    line (a perfect-prediction diagonal).

    Requires a supervised, regression-task ``ml.FittedModel`` (raises
    :class:`~emergentflow.explain.errors.UnsupportedModelError` otherwise -- classification,
    clustering, and fitted transformers are all rejected). Never mutates *frame*.
    """
    import plotly.graph_objects as go

    X, y_true = _require_regression_model(model, frame)
    y_pred = model.estimator.predict(X)

    fig = go.Figure(go.Scatter(x=y_true.tolist(), y=y_pred.tolist(), mode="markers"))
    lo = float(min(y_true.min(), y_pred.min()))
    hi = float(max(y_true.max(), y_pred.max()))
    fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line={"dash": "dash"})
    fig.update_layout(title="Predicted vs Actual", xaxis_title="Actual", yaxis_title="Predicted")
    return PlotSpec.from_figure("predicted_vs_actual", fig)


@public_op(name="ef.explain.plot_residuals")
def plot_residuals(model: FittedModel, frame: pd.DataFrame) -> PlotSpec:
    """Scatter of predicted values vs. residuals for a fitted regression model, with a
    residual=0 reference line.

    ``residual = actual - prediction``, matching this codebase's existing statsmodels-residual
    sign convention (``emergentflow.viz._model_data.model_residuals``). Requires a supervised,
    regression-task ``ml.FittedModel`` (raises
    :class:`~emergentflow.explain.errors.UnsupportedModelError` otherwise). Never mutates *frame*.
    """
    import plotly.graph_objects as go

    X, y_true = _require_regression_model(model, frame)
    y_pred = model.estimator.predict(X)
    residual = y_true - y_pred

    fig = go.Figure(go.Scatter(x=y_pred.tolist(), y=residual.tolist(), mode="markers"))
    fig.add_hline(y=0, line_dash="dash")
    fig.update_layout(
        title="Residuals vs Predicted", xaxis_title="Predicted", yaxis_title="Residual"
    )
    return PlotSpec.from_figure("residuals_vs_predicted", fig)


def _require_binary_classification_model(
    model: FittedModel, frame: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, Any]:
    """Validate *model* is a fitted, BINARY-classification ``ml.FittedModel`` with a
    ``predict_proba`` method and all its feature/target columns present in *frame*; return
    ``(y_true_binary, y_proba_positive, pos_label)`` where ``y_true_binary`` is a 0/1 array (1
    means the positive class, ``model.estimator.classes_[1]``, mirroring
    ``ef.ml.evaluate``'s existing ``pos_label = classes[1]`` convention) and
    ``y_proba_positive`` is that class's predicted probability for every row.

    Shared by :func:`plot_calibration` and :func:`plot_roc_pr`. Raises
    :class:`~emergentflow.explain.errors.UnsupportedModelError` for a non-classification model, a
    non-binary classifier, or an estimator with no ``predict_proba``.
    """
    if not isinstance(model, FittedModel) or model.target is None:
        raise UnsupportedModelError(
            "this plot requires a supervised FittedModel (ml.fit_estimator's 'fit' archetype); "
            "clustering models and fitted transformers are not supported."
        )
    if model.task != "classification":
        raise UnsupportedModelError(
            f"this plot requires a classification model; got task={model.task!r}."
        )
    if not hasattr(model.estimator, "predict_proba"):
        raise UnsupportedModelError(
            f"{model.estimator_type} has no predict_proba; this plot requires a "
            "probability-capable estimator."
        )
    classes = list(model.estimator.classes_)
    if len(classes) != 2:
        raise UnsupportedModelError(
            f"this plot requires a binary classifier; got {len(classes)} classes."
        )
    if model.target not in frame.columns:
        raise ValueError(f"missing target column {model.target!r}.")
    missing = [c for c in model.feature_names if c not in frame.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")

    X = frame[model.feature_names]
    y_true = frame[model.target].to_numpy()
    pos_label = classes[1]
    y_true_binary = (y_true == pos_label).astype(int)
    y_proba_positive = model.estimator.predict_proba(X)[:, 1]
    return y_true_binary, y_proba_positive, pos_label


@public_op(name="ef.explain.plot_calibration")
def plot_calibration(model: FittedModel, frame: pd.DataFrame, *, n_bins: int = 10) -> PlotSpec:
    """Build a reliability diagram (calibration curve) for a fitted BINARY classifier.

    Bins predicted probabilities into *n_bins* buckets (via
    ``sklearn.calibration.calibration_curve``) and plots each bucket's mean predicted probability
    against the observed fraction of positives, with a diagonal reference line (perfect
    calibration). Requires a binary classifier with ``predict_proba`` (raises
    :class:`~emergentflow.explain.errors.UnsupportedModelError` otherwise -- regression,
    clustering, fitted transformers, and multiclass classifiers are all rejected). Never mutates
    *frame*.
    """
    import plotly.graph_objects as go
    from sklearn.calibration import calibration_curve

    y_true_binary, y_proba_positive, pos_label = _require_binary_classification_model(model, frame)
    prob_true, prob_pred = calibration_curve(y_true_binary, y_proba_positive, n_bins=n_bins)

    fig = go.Figure(
        go.Scatter(x=prob_pred.tolist(), y=prob_true.tolist(), mode="markers+lines", name="Model")
    )
    fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line={"dash": "dash"})
    fig.update_layout(
        title=f"Calibration Curve (positive class: {pos_label!r})",
        xaxis_title="Mean predicted probability",
        yaxis_title="Observed fraction of positives",
    )
    return PlotSpec.from_figure("calibration", fig)


@public_op(name="ef.explain.plot_roc_pr")
def plot_roc_pr(model: FittedModel, frame: pd.DataFrame, *, curve: str = "roc") -> PlotSpec:
    """Build an ROC curve or a Precision-Recall curve for a fitted BINARY classifier.

    ``curve="roc"`` (the default) plots the false-positive rate vs. the true-positive rate, with
    a diagonal no-skill reference line, labeled with the AUC score. ``curve="pr"`` plots recall
    vs. precision, labeled with its own AUC score. Requires a binary classifier with
    ``predict_proba`` (raises :class:`~emergentflow.explain.errors.UnsupportedModelError`
    otherwise). Raises ``ValueError`` if *curve* is not ``"roc"`` or ``"pr"``. Never mutates
    *frame*.
    """
    import plotly.graph_objects as go
    from sklearn.metrics import auc, precision_recall_curve, roc_curve

    if curve not in ("roc", "pr"):
        raise ValueError(f"unknown curve {curve!r}; expected one of ('roc', 'pr').")
    y_true_binary, y_proba_positive, _pos_label = _require_binary_classification_model(model, frame)

    if curve == "roc":
        fpr, tpr, _ = roc_curve(y_true_binary, y_proba_positive)
        auc_score = float(auc(fpr, tpr))
        fig = go.Figure(
            go.Scatter(
                x=fpr.tolist(),
                y=tpr.tolist(),
                mode="lines",
                name=f"ROC (AUC={auc_score:.3f})",
            )
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line={"dash": "dash"})
        fig.update_layout(
            title="ROC Curve", xaxis_title="False Positive Rate", yaxis_title="True Positive Rate"
        )
        return PlotSpec.from_figure("roc_curve", fig)

    precision, recall, _ = precision_recall_curve(y_true_binary, y_proba_positive)
    auc_score = float(auc(recall, precision))
    fig = go.Figure(
        go.Scatter(
            x=recall.tolist(), y=precision.tolist(), mode="lines", name=f"PR (AUC={auc_score:.3f})"
        )
    )
    fig.update_layout(title="Precision-Recall Curve", xaxis_title="Recall", yaxis_title="Precision")
    return PlotSpec.from_figure("pr_curve", fig)
