"""
emergentflow.ml
~~~~~~~~~~~~~
Classical machine-learning operations (Epic 1, Story 8).

A thin wrapper over scikit-learn's ``LogisticRegression``. Each public
operation validates its inputs at the boundary (fail fast, clear typed
errors) and otherwise defers entirely to the underlying, trusted library —
no reimplementation, no hidden transformation.

The fitted estimator is intentionally **not** returned: it is an opaque,
library-internal handle and is forbidden as a public-op return under Story 7
rule 4 (serializable + inspectable returns). Instead, callers receive a
:class:`ClassifierResult` — a plain dataclass of inspectable metrics
(accuracy, split sizes, classes, feature names, and coefficients).

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split as _sk_split

from emergentflow.api import public_op
from emergentflow.ml.errors import InvalidEstimatorParamsError, UnknownEstimatorError
from emergentflow.ml.registry import get_estimator_spec

__all__ = [
    "FOREST_TASKS",
    "apply_estimator",
    "evaluate",
    "fit_estimator",
    "predict",
    "summarize",
    "train_classifier",
    "train_random_forest",
    "train_regressor",
    "train_test_split",
    "ClassifierResult",
    "EvaluationResult",
    "FittedModel",
    "FittedTransformer",
]

FOREST_TASKS = ("classification", "regression")


@dataclass
class ClassifierResult:
    """Inspectable summary of a trained classifier (never the model itself).

    Attributes
    ----------
    accuracy: held-out accuracy on the test split.
    n_train: number of rows used for training.
    n_test: number of rows used for evaluation.
    classes: class labels, in the order ``coefficients`` rows correspond to.
    feature_names: feature columns, in the order ``coefficients`` columns
        correspond to.
    coefficients: logistic-regression coefficients, one row per class (or a
        single row for binary classification) and one column per feature.
    """

    accuracy: float
    n_train: int
    n_test: int
    classes: list[str]
    feature_names: list[str]
    coefficients: list[list[float]]


@dataclass
class FittedModel:
    """A fitted estimator plus inspectable metadata (the Story 6 model representation).

    The live sklearn ``estimator`` rides in a field so the model can flow train -> predict/evaluate
    in-memory (execute) and as a plain variable (compiled code). The dataclass is inspectable by the
    ``@public_op`` contract; when surfaced to the result-payload contract the ``estimator`` field
    simply degrades to ``{"kind": "unsupported"}`` (it is never meant to be rendered).

    ``target`` is ``None`` for the ``cluster_detect`` archetype (Epic 8, Story 2), which has no
    target column; every other producer of ``FittedModel`` sets it to the trained target column.
    """

    estimator_type: str  # e.g. "LinearRegression", "RandomForestClassifier"
    task: str  # "classification" | "regression" | "clustering"
    feature_names: list[str]
    target: str | None
    estimator: Any  # live sklearn estimator; not JSON-serialized


@dataclass
class FittedTransformer:
    """A fitted unsupervised transformer plus inspectable metadata (Epic 8, Story 2).

    The ``fit_transform`` archetype's model representation, mirroring :class:`FittedModel`: the
    live sklearn ``transformer`` rides in a field so it can flow fit -> transform in-memory
    (execute) and as a plain variable (compiled code). Inspectable under the ``@public_op``
    contract; the ``transformer`` field degrades to ``{"kind": "unsupported"}`` on the
    result-payload contract, exactly like ``FittedModel.estimator``.
    """

    estimator_type: str  # e.g. "StandardScaler", "PCA"
    feature_names: list[str]
    transformer: Any  # live sklearn transformer; not JSON-serialized


@dataclass
class EvaluationResult:
    """Inspectable evaluation metrics for a fitted model on a dataset."""

    task: str
    n: int
    metrics: dict[str, float]


@public_op(name="ef.ml.evaluate")
def evaluate(model: FittedModel, df: pd.DataFrame) -> EvaluationResult:
    """Score a fitted model against the true ``model.target`` in ``df``.

    Regression metrics: ``r2``, ``mae``, ``rmse``. Classification metrics: ``accuracy`` always,
    plus ``precision``/``recall``/``f1`` (binary) or their ``_macro``/``_weighted`` variants
    (multiclass, via ``sklearn.metrics.classification_report``), plus ``roc_auc`` when the task is
    binary, the estimator exposes ``predict_proba``, and it is defined for ``df`` (skipped when
    ``df`` contains only one of the two classes). Only ``accuracy`` is reported if the fitted
    estimator was trained on a single class (``classes_`` has fewer than 2 entries), since
    precision/recall/f1/roc_auc are undefined in that degenerate case. Validates
    that the target and feature columns are present. Never mutates ``df``.
    """
    if model.target not in df.columns:
        raise ValueError(f"missing target column {model.target!r}.")
    missing = [c for c in model.feature_names if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")
    y_true = df[model.target]
    y_pred = model.estimator.predict(df[model.feature_names])
    if model.task == "regression":
        rmse = float(mean_squared_error(y_true, y_pred)) ** 0.5
        metrics = {
            "r2": float(r2_score(y_true, y_pred)),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": rmse,
        }
    else:  # classification
        metrics = {"accuracy": float(accuracy_score(y_true, y_pred))}
        classes = getattr(model.estimator, "classes_", None)
        n_classes = len(classes) if classes is not None else len(set(y_true))
        if n_classes > 2:
            report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
            metrics["precision_macro"] = float(report["macro avg"]["precision"])
            metrics["recall_macro"] = float(report["macro avg"]["recall"])
            metrics["f1_macro"] = float(report["macro avg"]["f1-score"])
            metrics["precision_weighted"] = float(report["weighted avg"]["precision"])
            metrics["recall_weighted"] = float(report["weighted avg"]["recall"])
            metrics["f1_weighted"] = float(report["weighted avg"]["f1-score"])
        elif n_classes == 2:
            pos_label = classes[1] if classes is not None else 1
            metrics["precision"] = float(
                precision_score(y_true, y_pred, zero_division=0, pos_label=pos_label)
            )
            metrics["recall"] = float(
                recall_score(y_true, y_pred, zero_division=0, pos_label=pos_label)
            )
            metrics["f1"] = float(f1_score(y_true, y_pred, zero_division=0, pos_label=pos_label))
            if hasattr(model.estimator, "predict_proba"):
                proba = model.estimator.predict_proba(df[model.feature_names])
                with contextlib.suppress(ValueError):
                    metrics["roc_auc"] = float(roc_auc_score(y_true, proba[:, 1]))
        # else: fewer than 2 classes in `classes_` (a degenerate single-class fit) --
        # precision/recall/f1/roc_auc are undefined, so only `accuracy` is reported.
    return EvaluationResult(task=model.task, n=int(df.shape[0]), metrics=metrics)


@public_op(name="ef.ml.summarize")
def summarize(model: FittedModel | FittedTransformer) -> dict[str, Any]:
    """Return a structural, inspectable summary of a fitted model/transformer.

    Looks up the estimator's registered ``summary_builder`` (Epic 8, Story 3) via
    ``get_estimator_spec(model.estimator_type)`` and calls it with the live fitted object.
    Returns ``{"kind": "unsupported"}`` if no summary builder is registered for this
    estimator, so a live estimator never has to be inspected directly.
    """
    try:
        spec = get_estimator_spec(model.estimator_type)
    except UnknownEstimatorError:
        return {"kind": "unsupported"}
    if spec.summary_builder is None:
        return {"kind": "unsupported"}
    live = model.estimator if isinstance(model, FittedModel) else model.transformer
    return spec.summary_builder(live)


@public_op(name="ef.ml.train_classifier")
def train_classifier(
    df: pd.DataFrame,
    *,
    target: str,
    features: list[str] | None = None,
    test_size: float = 0.25,
    random_state: int = 0,
) -> ClassifierResult:
    """Train a logistic-regression classifier and return inspectable metrics.

    Thin wrapper over scikit-learn. Deterministic given ``random_state``. The
    fitted estimator is deliberately not returned (Story 7, rule 4).
    """
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    feature_names = features if features is not None else [c for c in df.columns if c != target]

    unknown = [c for c in feature_names if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown features {unknown!r}; expected one of {list(df.columns)!r}.")
    if target in feature_names:
        raise ValueError(f"target {target!r} must not also appear in features {feature_names!r}.")

    X = df[feature_names]
    y = df[target]

    X_train, X_test, y_train, y_test = _sk_split(
        X, y, test_size=test_size, random_state=random_state
    )

    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train, y_train)

    acc = float(accuracy_score(y_test, model.predict(X_test)))

    return ClassifierResult(
        accuracy=acc,
        n_train=int(len(X_train)),
        n_test=int(len(X_test)),
        classes=[str(c) for c in model.classes_],
        feature_names=list(feature_names),
        coefficients=[[float(v) for v in row] for row in model.coef_],
    )


@public_op(name="ef.ml.train_regressor")
def train_regressor(
    df: pd.DataFrame,
    *,
    target: str,
    features: list[str] | None = None,
) -> FittedModel:
    """Fit a linear-regression model and return a :class:`FittedModel`.

    Thin wrapper over ``sklearn.linear_model.LinearRegression``. Deterministic. The fitted
    estimator rides inside the returned ``FittedModel`` (task ``"regression"``).
    """
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    feature_names = features if features is not None else [c for c in df.columns if c != target]

    unknown = [c for c in feature_names if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown features {unknown!r}; expected one of {list(df.columns)!r}.")
    if target in feature_names:
        raise ValueError(f"target {target!r} must not also appear in features {feature_names!r}.")

    X = df[feature_names]
    y = df[target]

    est = LinearRegression().fit(X, y)
    return FittedModel(
        estimator_type="LinearRegression",
        task="regression",
        feature_names=list(feature_names),
        target=target,
        estimator=est,
    )


@public_op(name="ef.ml.train_random_forest")
def train_random_forest(
    df: pd.DataFrame,
    *,
    target: str,
    features: list[str] | None = None,
    task: str = "classification",
    n_estimators: int = 100,
    random_state: int = 0,
) -> FittedModel:
    """Fit a random-forest model and return a :class:`FittedModel`.

    ``task="classification"`` fits a ``RandomForestClassifier``; ``"regression"`` a
    ``RandomForestRegressor``. Deterministic given ``random_state``.
    """
    if task not in FOREST_TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {list(FOREST_TASKS)!r}.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    feature_names = features if features is not None else [c for c in df.columns if c != target]

    unknown = [c for c in feature_names if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown features {unknown!r}; expected one of {list(df.columns)!r}.")
    if target in feature_names:
        raise ValueError(f"target {target!r} must not also appear in features {feature_names!r}.")

    X = df[feature_names]
    y = df[target]

    cls = RandomForestClassifier if task == "classification" else RandomForestRegressor
    est = cls(n_estimators=n_estimators, random_state=random_state).fit(X, y)
    return FittedModel(
        estimator_type=type(est).__name__,
        task=task,
        feature_names=list(feature_names),
        target=target,
        estimator=est,
    )


@public_op(name="ef.ml.predict")
def predict(model: FittedModel, df: pd.DataFrame) -> pd.DataFrame:
    """Apply a fitted model to ``df``, returning a NEW frame with a ``prediction`` column.

    Validates that every ``model.feature_names`` column is present. Never mutates ``df``.
    """
    missing = [c for c in model.feature_names if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")
    result = df.copy()
    result["prediction"] = model.estimator.predict(df[model.feature_names])
    return result


@public_op(name="ef.ml.train_test_split")
def train_test_split(
    df: pd.DataFrame,
    *,
    test_size: float = 0.25,
    random_state: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a DataFrame into (train, test) frames. Deterministic given ``random_state``.

    Thin wrapper over ``sklearn.model_selection.train_test_split``. Returns two NEW frames with
    reset indices. A tuple of tidy DataFrames is inspectable under the ``@public_op`` contract.
    """
    if not 0.0 < test_size < 1.0:
        raise ValueError(f"test_size must be in (0, 1); got {test_size!r}.")
    train_df, test_df = _sk_split(df, test_size=test_size, random_state=random_state)
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)


def _resolve_features_for_fit(
    df: pd.DataFrame, features: list[str] | None, *, target: str | None
) -> list[str]:
    """Resolve the feature-column list for a fit call, mirroring the train_* validation above.

    Defaults to every column except ``target`` when ``features`` is not given. Validates that
    every named feature exists in ``df`` and that ``target`` (if given) is not also a feature.
    """
    feature_names = features if features is not None else [c for c in df.columns if c != target]
    unknown = [c for c in feature_names if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown features {unknown!r}; expected one of {list(df.columns)!r}.")
    if target is not None and target in feature_names:
        raise ValueError(f"target {target!r} must not also appear in features {feature_names!r}.")
    return feature_names


@public_op(name="ef.ml.fit_estimator")
def fit_estimator(
    df: pd.DataFrame,
    *,
    estimator: str,
    target: str | None = None,
    features: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> FittedModel | FittedTransformer:
    """Fit a curated, allow-listed sklearn estimator and return an inspectable fitted wrapper.

    The single adapter every archetype node routes through (Epic 8, Story 2 / ADR 0016).
    ``estimator`` is validated against the allow-list registry
    (:func:`emergentflow.ml.registry.get_estimator_spec`, which raises
    :class:`~emergentflow.ml.errors.UnknownEstimatorError` for an unregistered key); ``params``
    keys are validated against that estimator's accepted-kwargs allow-list, raising
    :class:`~emergentflow.ml.errors.InvalidEstimatorParamsError` for unknown keys.

    Dispatches on the estimator's registered archetype (ADR 0016 subsection 3):

    * ``"fit"`` (supervised) requires ``target`` and returns a :class:`FittedModel` with
      ``task`` taken from the registry entry (``"classification"`` or ``"regression"``).
    * ``"cluster_detect"`` (unsupervised label/score) ignores ``target`` and returns a
      :class:`FittedModel` with ``task="clustering"`` and ``target=None``.
    * ``"fit_transform"`` (unsupervised transformer) ignores ``target`` and returns a
      :class:`FittedTransformer`.

    Deterministic given a ``random_state`` kwarg where the underlying estimator accepts one.
    Never mutates ``df``.
    """
    spec = get_estimator_spec(estimator)

    provided_params = params or {}
    unknown_params = [k for k in provided_params if k not in spec.accepted_kwargs]
    if unknown_params:
        raise InvalidEstimatorParamsError(
            f"unknown params {unknown_params!r} for estimator {estimator!r}; "
            f"expected one of {sorted(spec.accepted_kwargs)!r}."
        )
    kwargs = {name: kwarg_spec.default for name, kwarg_spec in spec.accepted_kwargs.items()}
    kwargs.update(provided_params)

    if spec.archetype == "fit":
        if target is None:
            raise ValueError(f"estimator {estimator!r} requires a target column.")
        if target not in df.columns:
            raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
        feature_names = _resolve_features_for_fit(df, features, target=target)
        est = spec.sklearn_class(**kwargs).fit(df[feature_names], df[target])
        return FittedModel(
            estimator_type=spec.key,
            task=spec.task or "classification",
            feature_names=list(feature_names),
            target=target,
            estimator=est,
        )

    if spec.archetype == "cluster_detect":
        feature_names = _resolve_features_for_fit(df, features, target=None)
        est = spec.sklearn_class(**kwargs).fit(df[feature_names])
        return FittedModel(
            estimator_type=spec.key,
            task=spec.task or "clustering",
            feature_names=list(feature_names),
            target=None,
            estimator=est,
        )

    # spec.archetype == "fit_transform"
    feature_names = _resolve_features_for_fit(df, features, target=None)
    est = spec.sklearn_class(**kwargs).fit(df[feature_names])
    return FittedTransformer(
        estimator_type=spec.key,
        feature_names=list(feature_names),
        transformer=est,
    )


@public_op(name="ef.ml.apply_estimator")
def apply_estimator(
    model: FittedModel | FittedTransformer,
    df: pd.DataFrame,
    *,
    op: str,
) -> pd.DataFrame:
    """Apply a fitted model/transformer to ``df``, returning a NEW frame. Never mutates ``df``.

    The apply archetype's backend (Epic 8, Story 2 / ADR 0016): every archetype's "consume a
    fitted Model/Transformer + a DataFrame" step routes through this one function, covering
    three ops:

    * ``"predict"`` requires a :class:`FittedModel` (``fit`` or ``cluster_detect`` archetype)
      and adds a ``prediction`` column, mirroring :func:`predict`.
    * ``"transform"`` requires a :class:`FittedTransformer` (``fit_transform`` archetype) and
      adds ``component_0``, ``component_1``, ... columns, one per output column of
      ``transformer.transform(...)``.
    * ``"score_samples"`` works on either wrapper's live object and adds a ``score`` column.

    Validates that every ``model.feature_names`` column is present in ``df``, that ``op`` is
    one of the three supported ops, that the underlying fitted object actually supports the
    requested op (e.g. calling ``"transform"`` against a :class:`FittedModel` -- a predictor,
    not a transformer -- raises ``ValueError``), and that the output column(s) the op would
    add do not already exist in ``df`` (to avoid silently overwriting real data).
    """
    if op not in ("predict", "transform", "score_samples"):
        raise ValueError(
            f"unknown op {op!r}; expected one of ('predict', 'transform', 'score_samples')."
        )
    missing = [c for c in model.feature_names if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")

    X = df[model.feature_names]
    result = df.copy()

    if op == "predict":
        if not isinstance(model, FittedModel):
            raise ValueError("predict requires a fitted Model (fit/cluster_detect archetype).")
        if not hasattr(model.estimator, "predict"):
            raise ValueError(f"{model.estimator_type} does not support predict.")
        if "prediction" in df.columns:
            raise ValueError("df already has a 'prediction' column; rename it before predicting.")
        result["prediction"] = model.estimator.predict(X)
        return result

    if op == "transform":
        if not isinstance(model, FittedTransformer):
            raise ValueError("transform requires a fitted Transformer (fit_transform archetype).")
        if not hasattr(model.transformer, "transform"):
            raise ValueError(f"{model.estimator_type} does not support transform.")
        transformed = model.transformer.transform(X)
        component_cols = [f"component_{i}" for i in range(transformed.shape[1])]
        collisions = [c for c in component_cols if c in df.columns]
        if collisions:
            raise ValueError(
                f"df already has columns {collisions!r}; rename them before transforming."
            )
        result[component_cols] = transformed
        return result

    # op == "score_samples"
    live = model.estimator if isinstance(model, FittedModel) else model.transformer
    if not hasattr(live, "score_samples"):
        raise ValueError(f"{model.estimator_type} does not support score_samples.")
    if "score" in df.columns:
        raise ValueError("df already has a 'score' column; rename it before scoring.")
    result["score"] = live.score_samples(X)
    return result


# Importing the seed catalog registers its estimator allow-list entries (LogisticRegression,
# StandardScaler, KMeans, GaussianMixture) into the registry the moment ``emergentflow.ml`` is
# imported — the same import-for-side-effect pattern ``emergentflow.types`` uses for its type
# catalog. Kept last so ``fit_estimator``/``get_estimator_spec`` are fully defined first. The
# lint suppression marks it as not-at-top (E402) and unused-but-intentional (F401).
from emergentflow.ml import catalog  # noqa: E402, F401
