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
from emergentflow.recommend import evaluate, recommend
from emergentflow.recommend.interactions import InteractionMatrix
from emergentflow.recommend.models import FittedRecommender
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
    "plot_missingness_heatmap",
    "plot_confusion_matrix",
    "plot_precision_recall_curve",
    "plot_metric_comparison",
    "plot_coverage_vs_accuracy",
    "plot_popularity_distribution",
    "plot_projection",
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
    if len(resid) < 2:
        # statsmodels acf/pacf require more than one observation (nobs must exceed the
        # requested lag count); a single residual cannot yield any autocorrelation lag. Raise
        # the module's typed, catchable error instead of leaking statsmodels' raw IndexError
        # or ValueError up to the caller.
        raise VizError(
            f"{kind.upper()} requires at least two residual observations to compute; "
            f"the fitted model produced {len(resid)}."
        )
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


@public_op(name="ef.viz.plot_missingness_heatmap")
def plot_missingness_heatmap(matrix: pd.DataFrame) -> PlotSpec:
    """Build a heatmap from a tidy co-missingness matrix (``emergentflow.stats.co_missingness``'s
    output: a leading ``"column"`` field of row labels, plus one column per variable, each cell
    the fraction of rows where both variables are null). Values are fractions in ``[0, 1]``
    rather than correlation's ``[-1, 1]``, so this uses a sequential (not diverging) colorscale
    and a fixed ``zmin=0``/``zmax=1`` range -- distinct from ``plot_correlation_heatmap`` rather
    than reusing it. Not part of the curated ``chart`` allow-list (``ef.viz.plot``); this is a
    bespoke plot built from ``go.Heatmap`` directly.
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
                zmin=0,
                zmax=1,
                colorscale="Reds",
                text=[[f"{v:.2f}" for v in row] for row in z],
                texttemplate="%{text}",
            )
        ]
    )
    fig.update_layout(title="Co-Missingness Heatmap")
    return PlotSpec.from_figure("missingness_heatmap", fig)


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


@public_op(name="ef.viz.plot_precision_recall_curve")
def plot_precision_recall_curve(
    recommender: FittedRecommender,
    test_interactions: InteractionMatrix,
    *,
    k_max: int = 50,
) -> PlotSpec:
    """Sweep k=1..k_max and plot the precision@k / recall@k trade-off for a fitted recommender.

    Calls the existing :func:`emergentflow.recommend.evaluate` once per k value (there is no
    single-call sklearn shortcut for recommender ranking metrics, unlike
    ``ef.explain.plot_roc_pr``'s ``sklearn.metrics.precision_recall_curve``), collecting
    ``(k, precision@k, recall@k)`` triples, then renders the classic precision-recall trade-off
    curve (x=recall, y=precision, one point per k, connected in k order). Raises
    :class:`~emergentflow.viz.errors.VizError` if ``k_max`` is not a positive integer.
    """
    import plotly.graph_objects as go

    if k_max < 1:
        raise VizError(f"k_max must be a positive integer; got {k_max!r}.")

    ks = list(range(1, k_max + 1))
    precisions = []
    recalls = []
    for k in ks:
        result = evaluate(
            recommender, test_interactions, k=k, metrics=["precision_at_k", "recall_at_k"]
        )
        precisions.append(result.aggregate["mean_precision_at_k"])
        recalls.append(result.aggregate["mean_recall_at_k"])

    fig = go.Figure(
        data=[
            go.Scatter(
                x=recalls,
                y=precisions,
                mode="lines+markers",
                text=[f"k={k}" for k in ks],
                hovertemplate="recall=%{x:.3f}<br>precision=%{y:.3f}<br>%{text}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=f"Precision-Recall Trade-off (k=1..{k_max}): {recommender.algorithm}",
        xaxis_title="Recall@k",
        yaxis_title="Precision@k",
    )
    return PlotSpec.from_figure("recommend_precision_recall_curve", fig)


#: Metric columns ef.recommend.compare() always produces (excluding "algorithm"/"is_baseline"),
#: in a sensible default display order.
_COMPARE_METRIC_COLUMNS = (
    "mean_precision_at_k",
    "mean_recall_at_k",
    "mean_ndcg_at_k",
    "hit_rate",
    "map_at_k",
    "mean_mrr_at_k",
    "mean_auc_at_k",
    "coverage",
    "diversity",
    "novelty",
)


@public_op(name="ef.viz.plot_metric_comparison")
def plot_metric_comparison(
    comparison: pd.DataFrame,
    *,
    metrics: list[str] | None = None,
) -> PlotSpec:
    """Grouped bar chart comparing multiple recommenders across metrics.

    Consumes the tidy comparison DataFrame produced by :func:`emergentflow.recommend.compare`
    (one row per recommender, an ``algorithm`` column, and one column per evaluation metric).
    One bar GROUP per recommender (x-axis = ``algorithm``), one COLOR per metric. ``metrics``
    selects which metric columns to plot; ``None`` (the default) plots every column in
    ``comparison`` that is one of the standard compare() metric columns
    (``mean_precision_at_k``, ``mean_recall_at_k``, ``mean_ndcg_at_k``, ``hit_rate``,
    ``map_at_k``, ``mean_mrr_at_k``, ``mean_auc_at_k``, ``coverage``, ``diversity``,
    ``novelty``) and is actually present in
    ``comparison`` (a caller may have passed a narrower ``metrics=`` subset into ``compare()``
    directly, in which case only the columns that survive are used). Raises
    :class:`~emergentflow.viz.errors.VizError` if ``comparison`` has no ``algorithm`` column,
    if an explicitly-requested metric in ``metrics`` is not a column of ``comparison``, or if
    the resolved metric list ends up empty.
    """
    import plotly.graph_objects as go

    if "algorithm" not in comparison.columns:
        raise VizError(
            f"comparison frame is missing an 'algorithm' column; got columns "
            f"{list(comparison.columns)!r}."
        )

    if metrics is not None:
        unknown = [m for m in metrics if m not in comparison.columns]
        if unknown:
            raise VizError(
                f"unknown metric column(s) {unknown!r}; comparison frame has columns "
                f"{list(comparison.columns)!r}."
            )
        resolved_metrics = list(metrics)
    else:
        resolved_metrics = [m for m in _COMPARE_METRIC_COLUMNS if m in comparison.columns]

    if not resolved_metrics:
        raise VizError("no metric columns to plot (resolved metric list is empty).")

    algorithms = comparison["algorithm"].tolist()
    fig = go.Figure(
        data=[
            go.Bar(name=metric, x=algorithms, y=comparison[metric].tolist())
            for metric in resolved_metrics
        ]
    )
    fig.update_layout(
        title="Recommender Metric Comparison",
        xaxis_title="Recommender",
        yaxis_title="Score",
        barmode="group",
    )
    return PlotSpec.from_figure("recommend_metric_comparison", fig)


@public_op(name="ef.viz.plot_coverage_vs_accuracy")
def plot_coverage_vs_accuracy(
    comparison: pd.DataFrame,
    *,
    accuracy_metric: str = "mean_ndcg_at_k",
) -> PlotSpec:
    """Scatter plot of each recommender's coverage against an accuracy metric (default NDCG@k).

    Consumes the tidy comparison DataFrame produced by :func:`emergentflow.recommend.compare`
    (one row per recommender, an ``algorithm`` column, a ``coverage`` column, and one column per
    other evaluation metric). Surfaces the classic accuracy/diversity trade-off: recommenders
    that concentrate on a narrow, highly-accurate slice of the catalog cluster in the top-left
    (high accuracy, low coverage); recommenders with broad catalog coverage but weaker accuracy
    cluster toward the bottom-right. Each point is labeled with its ``algorithm`` name. Raises
    :class:`~emergentflow.viz.errors.VizError` if ``comparison`` is missing an ``algorithm``
    column, a ``coverage`` column, or the requested ``accuracy_metric`` column.
    """
    import plotly.graph_objects as go

    missing = [c for c in ("algorithm", "coverage", accuracy_metric) if c not in comparison.columns]
    if missing:
        raise VizError(
            f"comparison frame is missing column(s) {missing!r}; got columns "
            f"{list(comparison.columns)!r}."
        )

    fig = go.Figure(
        data=[
            go.Scatter(
                x=comparison["coverage"].tolist(),
                y=comparison[accuracy_metric].tolist(),
                mode="markers+text",
                text=comparison["algorithm"].tolist(),
                textposition="top center",
            )
        ]
    )
    fig.update_layout(
        title="Coverage vs. Accuracy",
        xaxis_title="Coverage",
        yaxis_title=accuracy_metric,
    )
    return PlotSpec.from_figure("recommend_coverage_vs_accuracy", fig)


@public_op(name="ef.viz.plot_popularity_distribution")
def plot_popularity_distribution(
    recommender: FittedRecommender,
    interactions: InteractionMatrix,
    *,
    n: int = 10,
) -> PlotSpec:
    """Long-tail histogram: recommendation frequency vs. item popularity rank (log scale).

    Ranks every item in *interactions* by total interaction count (rank 1 = most popular),
    generates top-``n`` recommendations for every user in *interactions* via the existing
    :func:`emergentflow.recommend.recommend` wrapper, and tallies how often each item appears
    across all users' recommendation lists. Plots recommendation frequency (y) against item
    popularity rank (x, log scale) -- a recommender biased toward popular items shows tall bars
    only at low rank (the left edge); a recommender that surfaces the long tail shows frequency
    spread across higher ranks too. Never densifies ``interactions.matrix``. Raises
    :class:`~emergentflow.viz.errors.VizError` if ``n`` is not a positive integer or
    ``interactions`` has zero items.
    """
    import numpy as np
    import plotly.graph_objects as go

    if n < 1:
        raise VizError(f"n must be a positive integer; got {n!r}.")
    if interactions.n_items == 0:
        raise VizError("interactions has zero items; cannot rank popularity.")

    popularity_counts = np.asarray(interactions.matrix.sum(axis=0)).ravel()
    order = np.argsort(-popularity_counts)
    ranked_item_ids = [interactions.item_ids[i] for i in order]
    rank_of_item = {item_id: rank + 1 for rank, item_id in enumerate(ranked_item_ids)}

    result = recommend(recommender, user_ids=None, n=n, exclude_known=True)
    frequency = result.recommendations["item_id"].value_counts()

    ranks = [rank_of_item[item_id] for item_id in ranked_item_ids]
    counts = [int(frequency.get(item_id, 0)) for item_id in ranked_item_ids]

    fig = go.Figure(data=[go.Bar(x=ranks, y=counts)])
    fig.update_xaxes(type="log")
    fig.update_layout(
        title=f"Item Popularity Distribution: {recommender.algorithm}",
        xaxis_title="Item Popularity Rank (log scale)",
        yaxis_title="Recommendation Frequency",
    )
    return PlotSpec.from_figure("recommend_popularity_distribution", fig)


@public_op(name="ef.viz.plot_projection")
def plot_projection(
    df: pd.DataFrame,
    *,
    x_col: str = "component_1",
    y_col: str = "component_2",
    color_col: str | None = None,
) -> PlotSpec:
    """Render a 2-D projection scatter plot, optionally colored by a label column.

    A convenience wrapper over ``ef.viz.plot(chart="scatter", ...)``, pre-filling the x/y
    encoding for the two leading coordinate columns a dimensionality-reduction op
    (``ef.ml.reduce_dimensions``) produces by default. Reuses the SAME curated Epic 12 chart
    adapter/allow-list as ``plot`` -- no new rendering path, no new chart registered.
    """
    if x_col not in df.columns:
        raise ValueError(f"unknown x_col {x_col!r}; expected one of {list(df.columns)!r}.")
    if y_col not in df.columns:
        raise ValueError(f"unknown y_col {y_col!r}; expected one of {list(df.columns)!r}.")
    encoding: dict[str, Any] = {"x": x_col, "y": y_col}
    if color_col is not None:
        if color_col not in df.columns:
            raise ValueError(
                f"unknown color_col {color_col!r}; expected one of {list(df.columns)!r}."
            )
        encoding["color"] = color_col
    return plot(df, chart="scatter", encoding=encoding)


# Register the curated seed chart catalog as an import-time side effect (mirrors
# emergentflow.stats importing its catalog, and emergentflow.types.catalog).
from emergentflow.viz import catalog  # noqa: E402, F401
