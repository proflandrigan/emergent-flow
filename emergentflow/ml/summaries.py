"""
emergentflow.ml.summaries
~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-family inspectable summary builders (Epic 8, Story 3).

Each function takes the ONE live, already-fitted sklearn estimator/transformer object and
returns a JSON-native dict describing what was fitted (never a held-out performance metric --
that is ``ef.ml.evaluate``'s job). Every value is a plain Python scalar/list/dict so the result
satisfies the ``@public_op`` inspectable contract with no further conversion. Attribute access
is defensive (``getattr(..., None)``) because different estimator classes in the same family
expose different fitted attributes (e.g. GaussianMixture has no ``labels_``, KMeans does).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def summarize_classifier(estimator: Any) -> dict[str, Any]:
    """Structural summary for a fitted classifier: classes + coefficients/importances."""
    summary: dict[str, Any] = {}
    classes = getattr(estimator, "classes_", None)
    if classes is not None:
        summary["classes"] = [str(c) for c in classes]
    coef = getattr(estimator, "coef_", None)
    if coef is not None:
        coef_arr = np.asarray(coef)
        summary["coefficients"] = (
            [float(v) for v in coef_arr]
            if coef_arr.ndim == 1
            else [[float(v) for v in row] for row in coef_arr]
        )
    elif getattr(estimator, "feature_importances_", None) is not None:
        summary["feature_importances"] = [float(v) for v in estimator.feature_importances_]
    return summary


def summarize_regressor(estimator: Any) -> dict[str, Any]:
    """Structural summary for a fitted regressor: coefficients/importances + intercept."""
    summary: dict[str, Any] = {}
    coef = getattr(estimator, "coef_", None)
    if coef is not None:
        coef_arr = np.asarray(coef)
        summary["coefficients"] = (
            [float(v) for v in coef_arr]
            if coef_arr.ndim == 1
            else [[float(v) for v in row] for row in coef_arr]
        )
    elif getattr(estimator, "feature_importances_", None) is not None:
        summary["feature_importances"] = [float(v) for v in estimator.feature_importances_]
    intercept = getattr(estimator, "intercept_", None)
    if intercept is not None:
        intercept_arr = np.asarray(intercept)
        summary["intercept"] = (
            float(intercept_arr) if intercept_arr.ndim == 0 else [float(v) for v in intercept_arr]
        )
    return summary


def summarize_decomposition(estimator: Any) -> dict[str, Any]:
    """Structural summary for a fitted decomposition/PCA-like transformer."""
    summary: dict[str, Any] = {}
    ratio = getattr(estimator, "explained_variance_ratio_", None)
    if ratio is not None:
        summary["explained_variance_ratio"] = [float(v) for v in ratio]
    n_components = getattr(estimator, "n_components_", None)
    if n_components is None:
        n_components = getattr(estimator, "n_components", None)
    if n_components is not None:
        summary["n_components"] = int(n_components)
    components = getattr(estimator, "components_", None)
    if components is not None:
        summary["components"] = [[float(v) for v in row] for row in components]
    return summary


def summarize_clustering(estimator: Any) -> dict[str, Any]:
    """Structural summary for a fitted clusterer/mixture model."""
    summary: dict[str, Any] = {}
    labels = getattr(estimator, "labels_", None)
    if labels is not None:
        unique, counts = np.unique(labels, return_counts=True)
        summary["cluster_sizes"] = {
            str(int(u)): int(c) for u, c in zip(unique, counts, strict=True)
        }
        summary["n_clusters"] = int(len(unique))
    elif getattr(estimator, "n_components", None) is not None:
        summary["n_clusters"] = int(estimator.n_components)
    inertia = getattr(estimator, "inertia_", None)
    if inertia is not None:
        summary["inertia"] = float(inertia)
    weights = getattr(estimator, "weights_", None)
    if weights is not None:
        summary["weights"] = [float(w) for w in weights]
    converged = getattr(estimator, "converged_", None)
    if converged is not None:
        summary["converged"] = bool(converged)
    return summary


def summarize_outlier(estimator: Any) -> dict[str, Any]:
    """Structural summary for a fitted outlier/novelty detector."""
    summary: dict[str, Any] = {}
    contamination = getattr(estimator, "contamination", None)
    if contamination is not None:
        summary["contamination"] = (
            contamination if isinstance(contamination, (int, float)) else str(contamination)
        )
    offset = getattr(estimator, "offset_", None)
    if offset is not None:
        summary["offset"] = float(offset)
    return summary


def summarize_preprocessing(estimator: Any) -> dict[str, Any]:
    """Structural summary for a fitted preprocessing transformer: fitted stats."""
    summary: dict[str, Any] = {}
    for attr, key in (
        ("mean_", "mean"),
        ("scale_", "scale"),
        ("var_", "variance"),
        ("data_min_", "data_min"),
        ("data_max_", "data_max"),
    ):
        value = getattr(estimator, attr, None)
        if value is not None:
            summary[key] = [float(v) for v in value]
    categories = getattr(estimator, "categories_", None)
    if categories is not None:
        summary["categories"] = [[str(v) for v in cat] for cat in categories]
    return summary
