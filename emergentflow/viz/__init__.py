"""
emergentflow.viz
~~~~~~~~~~~~~~~~~
Visualization operations (Epic 12): one ``viz.plot`` archetype over a curated, generated chart
catalog, each returning a JSON-native ``PlotSpec`` (``fig.to_json()``-derived). Mirrors the
Epic 8 estimator-adapter move -- breadth as data over one archetype -- so ADR-0002 equivalence and
the ``@public_op`` inspectable contract hold by construction across the whole chart surface.

See ``docs/stats-viz-design.md``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.ml import FittedModel
from emergentflow.stats.models import FittedStatsModel
from emergentflow.viz._model_data import model_fitted, model_residuals
from emergentflow.viz.errors import (
    InvalidEncodingError,
    UnknownChartError,
    VizError,
)
from emergentflow.viz.models import PlotSpec
from emergentflow.viz.registry import ChartSpec, known_chart_keys
from emergentflow.viz.spec import _prepare_chart_spec

__all__ = [
    "PlotSpec",
    "ChartSpec",
    "VizError",
    "UnknownChartError",
    "InvalidEncodingError",
    "known_chart_keys",
    "plot",
    "plot_coefficients",
    "plot_residuals",
    "plot_acf",
    "plot_qq",
    "plot_correlation_heatmap",
    "plot_confusion_matrix",
]


@public_op(name="ef.viz.plot")
def plot(
    df: pd.DataFrame,
    *,
    chart: str,
    encoding: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> PlotSpec:
    """Build a curated, allow-listed plotly chart and return a JSON-native ``PlotSpec``.

    The single seam every viz node routes through (Epic 12, Story 2). ``chart`` is validated
    against the chart allow-list registry and ``encoding``/``options`` against the shared
    ``_prepare_chart_spec`` gate (raising :class:`~emergentflow.viz.errors.UnknownChartError` /
    :class:`~emergentflow.viz.errors.InvalidEncodingError`). The resolved chart's
    ``plotly.express`` function is called with the validated encoding + option kwargs, and the
    figure is serialized to a JSON-native ``PlotSpec`` (no live plotly ``Figure`` escapes). Because
    both ``compile_to_code``'s emitted code and ``execute`` reach a chart only through this
    function, ADR-0002 equivalence holds by construction. Never mutates ``df``.
    """
    import plotly.express as px

    chart_spec, resolved_encoding, resolved_options = _prepare_chart_spec(
        df, chart, encoding or {}, options or {}
    )
    px_fn = getattr(px, chart_spec.px_function)
    fig = px_fn(df, **resolved_encoding, **resolved_options)
    return PlotSpec.from_figure(chart, fig)


@public_op(name="ef.viz.plot_coefficients")
def plot_coefficients(model: FittedStatsModel) -> PlotSpec:
    """Build a coefficient / forest plot from a fitted model's tidy coefficient frame.

    Plots each ``term`` (y-axis, one row per fitted coefficient / variance component) against
    its point ``estimate`` (x-axis) with asymmetric whiskers from ``ci_low``/``ci_high``, plus a
    dashed reference line at zero. Rows with no defined CI (e.g. a mixed-effects model's
    variance-component rows, Story 5) simply render without a whisker -- they are never dropped
    from the plot. Not part of the curated ``chart`` allow-list (``ef.viz.plot``); this is a
    bespoke, model-aware plot that reads a ``FittedStatsModel`` directly, mirroring how
    ``ef.stats.fit_model`` is itself one of several archetype-specific wrappers rather than a
    single generic adapter.
    """
    import plotly.graph_objects as go

    coefficients = model.coefficients
    fig = go.Figure(
        data=[
            go.Scatter(
                x=coefficients["estimate"].tolist(),
                y=coefficients["term"].tolist(),
                mode="markers",
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": (coefficients["ci_high"] - coefficients["estimate"])
                    .fillna(0)
                    .tolist(),
                    "arrayminus": (coefficients["estimate"] - coefficients["ci_low"])
                    .fillna(0)
                    .tolist(),
                },
            )
        ]
    )
    fig.add_vline(x=0, line_dash="dash")
    fig.update_layout(
        title=f"Coefficients: {model.model}",
        xaxis_title="Estimate",
        yaxis_title="Term",
    )
    return PlotSpec.from_figure("coefficients", fig)


@public_op(name="ef.viz.plot_residuals")
def plot_residuals(model: FittedStatsModel) -> PlotSpec:
    """Build a fitted-values-vs-residuals scatter plot from a fitted model.

    Plots ``model.results.fittedvalues`` (x-axis) against the model's residuals (y-axis, via
    :func:`~emergentflow.viz._model_data.model_residuals`, which tolerates GLM/GAM's
    ``resid_response``), plus a dashed reference line at zero. Not part of the curated ``chart``
    allow-list (``ef.viz.plot``); this is a bespoke, model-aware plot that reads a
    ``FittedStatsModel`` directly.
    """
    import plotly.graph_objects as go

    fitted = list(model_fitted(model))
    resid = list(model_residuals(model))
    fig = go.Figure(data=[go.Scatter(x=fitted, y=resid, mode="markers")])
    fig.add_hline(y=0, line_dash="dash")
    fig.update_layout(
        title=f"Residuals: {model.model}",
        xaxis_title="Fitted values",
        yaxis_title="Residuals",
    )
    return PlotSpec.from_figure("residuals", fig)


@public_op(name="ef.viz.plot_qq")
def plot_qq(model: FittedStatsModel) -> PlotSpec:
    """Build a Q-Q (quantile-quantile) plot of a fitted model's residuals against a normal.

    Uses ``scipy.stats.probplot`` to compute theoretical-vs-ordered-residual quantile pairs and
    a best-fit reference line, plotted as a scatter of points plus the reference line. Residuals
    come from :func:`~emergentflow.viz._model_data.model_residuals` (tolerates GLM/GAM's
    ``resid_response``). Not part of the curated ``chart`` allow-list (``ef.viz.plot``); this is
    a bespoke, model-aware plot that reads a ``FittedStatsModel`` directly.
    """
    import plotly.graph_objects as go
    from scipy import stats

    resid = model_residuals(model)
    (theoretical, ordered), (slope, intercept, _r) = stats.probplot(resid, dist="norm")
    theoretical = theoretical.tolist()
    ordered = ordered.tolist()
    reference_line = [slope * q + intercept for q in theoretical]

    fig = go.Figure(
        data=[
            go.Scatter(x=theoretical, y=ordered, mode="markers", name="Residuals"),
            go.Scatter(x=theoretical, y=reference_line, mode="lines", name="Reference"),
        ]
    )
    fig.update_layout(
        title=f"Q-Q Plot: {model.model}",
        xaxis_title="Theoretical Quantiles",
        yaxis_title="Ordered Residuals",
    )
    return PlotSpec.from_figure("qq", fig)


@public_op(name="ef.viz.plot_acf")
def plot_acf(model: FittedStatsModel, *, kind: str = "acf", nlags: int = 20) -> PlotSpec:
    """Build an ACF or PACF bar plot of a fitted model's residuals, with a 95% CI band.

    ``kind`` selects ``statsmodels.tsa.stattools.acf`` (autocorrelation) or ``.pacf`` (partial
    autocorrelation); raises :class:`~emergentflow.viz.errors.VizError` for any other value.
    Residuals come from :func:`~emergentflow.viz._model_data.model_residuals` (tolerates GLM/GAM's
    ``resid_response``). ``nlags`` is clamped to at most ``len(residuals) // 2 - 1`` (statsmodels
    raises above that bound) rather than erroring on a short residual series. Not part of the
    curated ``chart`` allow-list (``ef.viz.plot``); this is a bespoke, model-aware plot that reads
    a ``FittedStatsModel`` directly.
    """
    import plotly.graph_objects as go
    from statsmodels.tsa.stattools import acf as _acf
    from statsmodels.tsa.stattools import pacf as _pacf

    if kind not in ("acf", "pacf"):
        raise VizError(f"kind must be 'acf' or 'pacf', got {kind!r}.")

    resid = model_residuals(model)
    max_lags = max(1, len(resid) // 2 - 1)
    lags = min(nlags, max_lags)
    fn = _acf if kind == "acf" else _pacf
    values, confint = fn(resid, nlags=lags, alpha=0.05)

    values_list = values.tolist()
    fig = go.Figure(
        data=[
            go.Bar(
                x=list(range(len(values_list))),
                y=values_list,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": (confint[:, 1] - values).tolist(),
                    "arrayminus": (values - confint[:, 0]).tolist(),
                },
            )
        ]
    )
    fig.update_layout(
        title=f"{kind.upper()}: {model.model}",
        xaxis_title="Lag",
        yaxis_title=kind.upper(),
    )
    return PlotSpec.from_figure(kind, fig)


@public_op(name="ef.viz.plot_correlation_heatmap")
def plot_correlation_heatmap(matrix: pd.DataFrame) -> PlotSpec:
    """Build a heatmap from a tidy correlation matrix (``emergentflow.stats.correlation``'s
    output: a leading ``"column"`` field of row labels, plus one column per correlated
    variable). Not part of the curated ``chart`` allow-list (``ef.viz.plot``) since
    ``plotly.express`` has no direct "matrix + row-label column" chart -- this is a bespoke plot
    built from ``go.Heatmap`` directly.
    """
    import plotly.graph_objects as go

    labels = matrix["column"].tolist()
    value_columns = [c for c in matrix.columns if c != "column"]
    z = matrix[value_columns].to_numpy().tolist()

    fig = go.Figure(
        data=[
            go.Heatmap(
                z=z,
                x=value_columns,
                y=labels,
                zmin=-1,
                zmax=1,
                colorscale="RdBu",
                text=[[f"{v:.2f}" for v in row] for row in z],
                texttemplate="%{text}",
            )
        ]
    )
    fig.update_layout(title="Correlation Heatmap")
    return PlotSpec.from_figure("correlation_heatmap", fig)


@public_op(name="ef.viz.plot_confusion_matrix")
def plot_confusion_matrix(model: FittedModel, frame: pd.DataFrame) -> PlotSpec:
    """Build a confusion-matrix heatmap for a fitted classifier scored against *frame*.

    Re-predicts ``model.estimator.predict(frame[model.feature_names])`` and compares against
    ``frame[model.target]`` (mirroring ``emergentflow.ml.evaluate``'s own validation style, but
    raising :class:`~emergentflow.viz.errors.VizError` instead of a bare ``ValueError``, since
    this is viz-package code). Raises if ``model.task`` is not ``"classification"`` -- a
    confusion matrix is undefined for regression/clustering. Not part of the curated ``chart``
    allow-list (``ef.viz.plot``); this is a bespoke plot built from ``go.Heatmap`` directly.
    """
    import plotly.graph_objects as go
    from sklearn.metrics import confusion_matrix

    if model.task != "classification":
        raise VizError(
            f"confusion matrix requires a classification model; got task={model.task!r}."
        )
    if model.target is None or model.target not in frame.columns:
        raise VizError(f"missing target column {model.target!r} in the input frame.")
    missing = [c for c in model.feature_names if c not in frame.columns]
    if missing:
        raise VizError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")

    y_true = frame[model.target]
    y_pred = model.estimator.predict(frame[model.feature_names])
    classes = list(model.estimator.classes_)
    labels = [str(c) for c in classes]
    cm = confusion_matrix(y_true, y_pred, labels=classes).tolist()

    fig = go.Figure(
        data=[
            go.Heatmap(
                z=cm,
                x=labels,
                y=labels,
                colorscale="Blues",
                text=[[str(v) for v in row] for row in cm],
                texttemplate="%{text}",
            )
        ]
    )
    fig.update_layout(
        title=f"Confusion Matrix: {model.estimator_type}",
        xaxis_title="Predicted",
        yaxis_title="Actual",
    )
    return PlotSpec.from_figure("confusion_matrix", fig)


# Register the curated seed chart catalog as an import-time side effect (mirrors
# emergentflow.stats importing its catalog, and emergentflow.types.catalog).
from emergentflow.viz import catalog  # noqa: E402, F401
