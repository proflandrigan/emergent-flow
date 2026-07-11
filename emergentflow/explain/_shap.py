"""
emergentflow.explain._shap
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Private SHAP explainer construction (ADR 0020, Decision clause 3). Lazily imports ``shap`` so a
bare ``import emergentflow`` and every non-SHAP explain.* op stay shap-free.

Dispatch: pure tree-ensemble regressors (``_TREE_ESTIMATOR_TYPES``) use ``shap.TreeExplainer``
directly on the fitted estimator -- exact, no background sampling, no seed needed. Every other
case (every classifier regardless of estimator type, and every non-tree regressor) uses
``shap.Explainer`` wrapping a plain predict callable over a seeded, bounded background sample
(SHAP's ``PermutationExplainer`` under the hood). Classification never uses ``TreeExplainer``: it
and the permutation path disagree on output units for a classifier (raw margin vs. probability)
unless ``TreeExplainer`` is separately reconfigured with its own background + ``model_output=
"probability"`` -- at that point it has the same background dependency as the permutation path
with none of the simplicity, so classification always takes the ``predict_proba`` path instead
(see ADR 0020, Consequences).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from emergentflow.explain.errors import MissingOptionalDependencyError, UnsupportedModelError
from emergentflow.ml import FittedModel

if TYPE_CHECKING:
    import shap  # noqa: F401 -- type-checking convenience, unused today

#: estimator_type keys shap.TreeExplainer supports exactly (pure tree ensembles curated in
#: emergentflow/ml/catalog.py). AdaBoost/Bagging are deliberately excluded: they are
#: meta-ensembles that may wrap an arbitrary base estimator and are not natively supported by
#: shap.TreeExplainer.
_TREE_ESTIMATOR_TYPES = frozenset(
    {
        "DecisionTreeClassifier",
        "DecisionTreeRegressor",
        "RandomForestClassifier",
        "RandomForestRegressor",
        "ExtraTreesClassifier",
        "ExtraTreesRegressor",
        "GradientBoostingClassifier",
        "GradientBoostingRegressor",
        "HistGradientBoostingClassifier",
        "HistGradientBoostingRegressor",
    }
)


def _import_shap() -> Any:
    try:
        import shap
    except ImportError:
        raise MissingOptionalDependencyError("emergentflow[explain]") from None
    return shap


def _predict_fn(model: FittedModel) -> Any:
    """The callable to explain: ``predict`` for regression, a ``predict_proba``-derived callable
    for classification. Binary classification returns ONLY the positive class's
    (``estimator.classes_[1]``) probability -- mirrors ``ef.ml.evaluate``'s existing
    ``pos_label = classes[1]`` convention for binary metrics; multiclass returns the full
    ``predict_proba`` matrix (one output column per class)."""
    if model.task == "regression":
        return model.estimator.predict
    if model.task != "classification":
        raise UnsupportedModelError(
            f"explain requires a classification or regression model; got task={model.task!r}."
        )
    if not hasattr(model.estimator, "predict_proba"):
        raise UnsupportedModelError(
            f"{model.estimator_type} has no predict_proba; classification explanations require "
            "a probability-capable estimator."
        )
    classes = model.estimator.classes_
    if len(classes) == 2:
        return lambda X: model.estimator.predict_proba(X)[:, 1]
    return model.estimator.predict_proba


def _validate_supervised_model(model: FittedModel, frame: pd.DataFrame) -> pd.DataFrame:
    """Validate *model* is a supervised fit-archetype FittedModel with all its feature columns
    present in *frame*, and return ``frame[model.feature_names]``."""
    if not isinstance(model, FittedModel) or model.target is None:
        raise UnsupportedModelError(
            "explain requires a supervised FittedModel (ml.fit_estimator's 'fit' archetype); "
            "clustering models and fitted transformers are not supported."
        )
    missing = [c for c in model.feature_names if c not in frame.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")
    return frame[model.feature_names]


def build_explanation(
    model: FittedModel, frame: pd.DataFrame, *, seed: int, background_samples: int
) -> Any:
    """Build a SHAP ``Explanation`` for *model* over *frame*'s feature columns.

    Raises :class:`~emergentflow.explain.errors.UnsupportedModelError` if *model* is not a
    supervised ``fit``-archetype :class:`~emergentflow.ml.FittedModel`, or if a classification
    model has no ``predict_proba``. Raises
    :class:`~emergentflow.explain.errors.MissingOptionalDependencyError` if ``shap`` is not
    installed.
    """
    shap = _import_shap()
    X = _validate_supervised_model(model, frame)

    if model.task == "regression" and model.estimator_type in _TREE_ESTIMATOR_TYPES:
        explainer = shap.TreeExplainer(model.estimator)
        return explainer(X)

    predict_fn = _predict_fn(model)
    n_background = min(background_samples, len(X))
    background = X.sample(n=n_background, random_state=seed)
    explainer = shap.Explainer(predict_fn, background, seed=seed)
    return explainer(X)


def _broadcast_base_values(base_values: Any, n_rows: int) -> np.ndarray:
    """Normalize a SHAP explanation's ``base_values`` (a scalar, or an array of shape ``(n,)``)
    to a length-``n_rows`` float array. TreeExplainer on a single-output regression task can
    return a bare scalar (one expected value shared by every row); PermutationExplainer always
    returns one value per row."""
    arr = np.asarray(base_values, dtype=float)
    if arr.ndim == 0:
        return np.full(n_rows, float(arr))
    if arr.shape == (n_rows,):
        return arr
    raise ValueError(f"unexpected base_values shape {arr.shape!r} for {n_rows} rows.")


def to_tidy_frame(explanation: Any, model: FittedModel, frame: pd.DataFrame) -> pd.DataFrame:
    """Convert a SHAP ``Explanation`` into the tidy, long-format DataFrame ADR 0020 Decision
    clause 4 specifies: one row per ``(row_index, feature[, class])``.

    Columns: ``row_index`` (0-indexed position in *frame*), ``feature``, ``feature_value``,
    ``shap_value``, ``base_value``, and -- ONLY for a multiclass classifier -- ``class`` (one
    block of rows per class, in ``model.estimator.classes_`` order). Binary classification and
    regression are single-output (no ``class`` column); see :func:`_predict_fn`.
    """
    X = frame[model.feature_names].reset_index(drop=True)
    n_rows = len(X)
    values = np.asarray(explanation.values, dtype=float)

    if values.ndim == 2:
        base = _broadcast_base_values(explanation.base_values, n_rows)
        records = [
            {
                "row_index": i,
                "feature": feat,
                "feature_value": X.iat[i, j],
                "shap_value": float(values[i, j]),
                "base_value": base[i],
            }
            for i in range(n_rows)
            for j, feat in enumerate(model.feature_names)
        ]
        return pd.DataFrame(records)

    # values.ndim == 3: (n_rows, n_features, n_classes) -- multiclass.
    classes = model.estimator.classes_
    base_values = np.asarray(explanation.base_values, dtype=float)
    records = []
    for k, cls in enumerate(classes):
        base_k = _broadcast_base_values(base_values[:, k], n_rows)
        for i in range(n_rows):
            for j, feat in enumerate(model.feature_names):
                records.append(
                    {
                        "row_index": i,
                        "feature": feat,
                        "feature_value": X.iat[i, j],
                        "shap_value": float(values[i, j, k]),
                        "base_value": base_k[i],
                        "class": cls,
                    }
                )
    return pd.DataFrame(records)
