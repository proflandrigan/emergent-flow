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
import importlib.util
import json
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    AdaBoostClassifier,
    AdaBoostRegressor,
    BaggingClassifier,
    BaggingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
    StackingClassifier,
    StackingRegressor,
    VotingClassifier,
    VotingRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_curve,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
from sklearn.model_selection import cross_validate as _sk_cross_validate
from sklearn.model_selection import train_test_split as _sk_split
from sklearn.pipeline import Pipeline as _SkPipeline
from tqdm import tqdm

from emergentflow import __version__
from emergentflow.api import public_op
from emergentflow.ir.common import ArtifactRef
from emergentflow.ml.errors import (
    InvalidEstimatorParamsError,
    MissingOptionalDependencyError,
    ModelPersistenceError,
    UnknownEstimatorError,
)
from emergentflow.ml.registry import get_estimator_spec, keys_for_archetype

__all__ = [
    "FOREST_TASKS",
    "apply_estimator",
    "blend_models",
    "calibrate_model",
    "compare_models",
    "cross_validate",
    "evaluate",
    "ensemble_model",
    "fit_and_detect",
    "fit_and_label",
    "fit_estimator",
    "fit_pipeline",
    "fit_transform",
    "finalize_model",
    "grid_search",
    "predict",
    "optimize_threshold",
    "reduce_dimensions",
    "select_features",
    "stack_models",
    "summarize",
    "train_classifier",
    "train_random_forest",
    "train_regressor",
    "train_test_split",
    "tune_model",
    "ClassifierResult",
    "DimensionReductionResult",
    "EvaluationResult",
    "FittedModel",
    "FittedTransformer",
    "ThresholdResult",
    "save_model",
    "load_model",
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

    ``target`` is ``None`` for the ``cluster_detect`` and ``outlier_detect`` archetypes
    (Epic 8, Story 2), which have no target column; every other producer of ``FittedModel``
    sets it to the trained target column.
    """

    estimator_type: str  # e.g. "LinearRegression", "RandomForestClassifier"
    task: str  # "classification" | "regression" | "clustering" | "outlier_detection"
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
    if "prediction" in df.columns:
        raise ValueError("df already has a 'prediction' column; rename it before predicting.")
    result = df.copy()
    result["prediction"] = model.estimator.predict(df[model.feature_names])
    return result


@public_op(name="ef.ml.ensemble_model")
def ensemble_model(
    model: FittedModel,
    df: pd.DataFrame,
    *,
    task: str,
    target: str,
    features: list[str] | None = None,
    method: str = "bagging",
    n_estimators: int = 10,
    random_state: int = 0,
) -> FittedModel:
    """Wrap a fitted estimator in a bagging/boosting ensemble and refit on ``df``.

    Mirrors PyCaret's ``ensemble_model``: the base estimator is recreated as an unfitted clone
    of the fitted model (via ``sklearn.base.clone``) because sklearn's Bagging/AdaBoost
    estimators require an unfitted base, then refit on ``df``.
    ``method="bagging"`` maps to Bagging; ``"boosting"`` to AdaBoost. Never mutates ``df`` or
    ``model``.
    """
    if method not in ("bagging", "boosting"):
        raise ValueError(f"unknown method {method!r}; expected 'bagging' or 'boosting'.")
    if task not in FOREST_TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {list(FOREST_TASKS)!r}.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
    feature_names = _resolve_features_for_fit(df, features, target=target)
    base = clone(model.estimator)
    if task == "classification":
        if method == "bagging":
            est = BaggingClassifier(
                estimator=base, n_estimators=n_estimators, random_state=random_state
            )
        else:
            est = AdaBoostClassifier(
                estimator=base, n_estimators=n_estimators, random_state=random_state
            )
    else:
        if method == "bagging":
            est = BaggingRegressor(
                estimator=base, n_estimators=n_estimators, random_state=random_state
            )
        else:
            est = AdaBoostRegressor(
                estimator=base, n_estimators=n_estimators, random_state=random_state
            )
    est.fit(df[feature_names], df[target])
    return FittedModel(
        estimator_type=type(est).__name__,
        task=task,
        feature_names=list(feature_names),
        target=target,
        estimator=est,
    )


@public_op(name="ef.ml.calibrate_model")
def calibrate_model(
    model: FittedModel,
    df: pd.DataFrame,
    *,
    target: str,
    features: list[str] | None = None,
    method: str = "sigmoid",
    cv: int = 5,
) -> FittedModel:
    """Probability-calibrate a fitted classifier via CalibratedClassifierCV, refit on df."""
    if model.task != "classification":
        raise ValueError("calibrate_model requires a classification model.")
    if method not in ("sigmoid", "isotonic"):
        raise ValueError(f"unknown method {method!r}; expected 'sigmoid' or 'isotonic'.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
    if not hasattr(model.estimator, "predict_proba"):
        raise ValueError(
            f"{model.estimator_type} does not support predict_proba; "
            "probability calibration requires it."
        )
    feature_names = _resolve_features_for_fit(df, features, target=target)
    base = clone(model.estimator)
    est = CalibratedClassifierCV(estimator=base, method=method, cv=cv)
    est.fit(df[feature_names], df[target])
    return FittedModel(
        estimator_type=type(est).__name__,
        task="classification",
        feature_names=list(feature_names),
        target=target,
        estimator=est,
    )


@dataclass
class ThresholdResult:
    """Result of decision-threshold optimization for a binary classifier."""

    best_threshold: float
    best_f1: float
    positive_class: str
    metrics: pd.DataFrame


@public_op(name="ef.ml.optimize_threshold")
def optimize_threshold(
    model: FittedModel,
    df: pd.DataFrame,
    *,
    target: str,
    positive_class: str | None = None,
) -> ThresholdResult:
    """Optimize the decision threshold of a binary classifier to maximize F1."""
    if model.task != "classification":
        raise ValueError("optimize_threshold requires a binary classification model.")
    if not hasattr(model.estimator, "predict_proba"):
        raise ValueError(f"{model.estimator_type} does not support predict_proba.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
    missing = [c for c in model.feature_names if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")

    X = df[model.feature_names]
    y = df[target]
    classes = model.estimator.classes_
    if len(classes) != 2:
        raise ValueError("optimize_threshold requires a binary (2-class) classifier.")
    pos = positive_class if positive_class is not None else str(classes[1])
    if pos not in {str(c) for c in classes}:
        raise ValueError(
            f"unknown positive_class {pos!r}; expected one of {[str(c) for c in classes]!r}."
        )
    pos_index = next(i for i, c in enumerate(classes) if str(c) == pos)

    prob_pos = model.estimator.predict_proba(X)[:, pos_index]
    # ``precision_recall_curve`` returns precision/recall arrays that are one element longer
    # than ``thresholds``: the trailing precision/recall is the "predict everything positive"
    # operating point (decision threshold of 0). Zipping against ``thresh`` alone would drop it,
    # so evaluate every operating point using threshold ``0`` for that final entry.
    prec, rec, thresh = precision_recall_curve(y, prob_pos, pos_label=classes[pos_index])

    rows = []
    best_t = 0.0
    best_f1 = 0.0
    n_thresh = len(thresh)
    for i, (p, r) in enumerate(zip(prec, rec, strict=True)):
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        t = float(thresh[i]) if i < n_thresh else 0.0
        rows.append((t, float(p), float(r), f1))
        if f1 > best_f1:
            best_f1 = f1
            best_t = t

    metrics = pd.DataFrame(rows, columns=["threshold", "precision", "recall", "f1"])
    return ThresholdResult(
        best_threshold=best_t,
        best_f1=float(best_f1),
        positive_class=pos,
        metrics=metrics,
    )


@public_op(name="ef.ml.finalize_model")
def finalize_model(
    model: FittedModel,
    df: pd.DataFrame,
    *,
    target: str | None = None,
) -> FittedModel:
    """Refit a fitted model on the full dataset with its fitted hyperparameters."""
    target = target if target is not None else model.target
    if target is None:
        raise ValueError("finalize_model requires a target column (e.g. from the model).")
    missing = [c for c in model.feature_names if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns {missing!r}; expected {model.feature_names!r}.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    est = type(model.estimator)(**model.estimator.get_params(deep=False))
    est.fit(df[model.feature_names], df[target])
    return FittedModel(
        estimator_type=model.estimator_type,
        task=model.task,
        feature_names=list(model.feature_names),
        target=target,
        estimator=est,
    )


@public_op(name="ef.ml.blend_models")
def blend_models(
    models: list[FittedModel],
    df: pd.DataFrame,
    *,
    task: str,
    target: str,
    features: list[str] | None = None,
    voting: str = "soft",
    weights: list[float] | None = None,
) -> FittedModel:
    """Blend several fitted estimators into a weighted voting ensemble, refit on ``df``.

    Mirrors PyCaret's ``blend_models``: each base estimator is recreated as an unfitted clone
    of the fitted model (via ``sklearn.base.clone``) because sklearn's Voting estimators require
    unfitted base clones. ``voting``
    only matters for classification; for regression it is validated but ignored. Never mutates
    ``models``, any model, or ``df``.
    """
    if task not in FOREST_TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {list(FOREST_TASKS)!r}.")
    if len(models) < 2:
        raise ValueError("blend_models requires at least two fitted models.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
    if voting not in ("soft", "hard"):
        raise ValueError(f"unknown voting {voting!r}; expected 'soft' or 'hard'.")
    feature_names = _resolve_features_for_fit(df, features, target=target)
    estimators = [(f"m{i}", clone(m.estimator)) for i, m in enumerate(models)]
    if task == "classification":
        est = VotingClassifier(
            estimators=estimators,
            voting=voting,
            weights=weights,
        )
    else:
        est = VotingRegressor(estimators=estimators, weights=weights)
    est.fit(df[feature_names], df[target])
    return FittedModel(
        estimator_type=type(est).__name__,
        task=task,
        feature_names=list(feature_names),
        target=target,
        estimator=est,
    )


@public_op(name="ef.ml.stack_models")
def stack_models(
    models: list[FittedModel],
    df: pd.DataFrame,
    *,
    task: str,
    target: str,
    features: list[str] | None = None,
    final_estimator: str | None = None,
    cv: int = 5,
) -> FittedModel:
    """Stack several fitted estimators under a curated meta-learner, refit on ``df``.

    Mirrors PyCaret's ``stack_models``: each base estimator is recreated as an unfitted clone
    of the fitted model (via ``sklearn.base.clone``) because sklearn's Stacking estimators
    require unfitted base clones, and the
    meta-learner ``final_estimator`` is trained via ``cv``-fold cross-validation. When
    ``final_estimator`` is ``None`` a task-appropriate meta-learner is chosen automatically
    (``LogisticRegression`` for classification, ``Ridge`` for regression). Never mutates
    ``models``, any model, or ``df``.
    """
    if task not in FOREST_TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {list(FOREST_TASKS)!r}.")
    if len(models) < 2:
        raise ValueError("stack_models requires at least two fitted models.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
    feature_names = _resolve_features_for_fit(df, features, target=target)
    estimators = [(f"m{i}", clone(m.estimator)) for i, m in enumerate(models)]
    meta_key = (
        final_estimator
        if final_estimator is not None
        else ("LogisticRegression" if task == "classification" else "Ridge")
    )
    meta_spec, meta_kwargs = _resolve_estimator_and_kwargs(meta_key, None)
    if meta_spec.task is not None and meta_spec.task != task:
        raise ValueError(
            f"final_estimator {meta_key!r} is a {meta_spec.task} model, but the stack "
            f"task is {task!r}; choose a {task} meta-learner."
        )
    meta = meta_spec.sklearn_class(**meta_kwargs)
    if task == "classification":
        est = StackingClassifier(estimators=estimators, final_estimator=meta, cv=cv)
    else:
        est = StackingRegressor(estimators=estimators, final_estimator=meta, cv=cv)
    est.fit(df[feature_names], df[target])
    return FittedModel(
        estimator_type=type(est).__name__,
        task=task,
        feature_names=list(feature_names),
        target=target,
        estimator=est,
    )


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


def _resolve_estimator_and_kwargs(
    estimator: str, params: dict[str, Any] | None
) -> tuple[Any, dict[str, Any]]:
    """Look up *estimator* in the allow-list registry and merge curated defaults with *params*.

    Shared by every ``ef.ml.*`` adapter entry point that constructs a curated estimator, so the
    unknown-estimator/unknown-params validation stays identical across the ``fit``,
    ``fit_transform``, and ``cluster_detect`` archetypes. Returns ``(spec, kwargs)``.
    """
    spec = get_estimator_spec(estimator)
    provided_params = params or {}
    unknown_params = [k for k in provided_params if k not in spec.accepted_kwargs]
    if unknown_params:
        raise InvalidEstimatorParamsError(
            f"unknown params {unknown_params!r} for estimator {estimator!r}; "
            f"expected one of {sorted(spec.accepted_kwargs)!r}."
        )
    kwargs: dict[str, Any] = {}
    for name, kwarg_spec in spec.accepted_kwargs.items():
        value = provided_params.get(name, kwarg_spec.default)
        if kwarg_spec.estimator_ref:
            nested_spec = get_estimator_spec(cast(str, value))
            if nested_spec.archetype != "fit":
                raise InvalidEstimatorParamsError(
                    f"{value!r} is not a fit-archetype estimator; {name!r} on "
                    f"estimator {estimator!r} requires a supervised classifier/regressor."
                )
            _, nested_kwargs = _resolve_estimator_and_kwargs(cast(str, value), None)
            value = nested_spec.sklearn_class(**nested_kwargs)
        elif kwarg_spec.choices is not None:
            if value not in kwarg_spec.choices:
                raise InvalidEstimatorParamsError(
                    f"{value!r} is not a valid {name!r} for estimator {estimator!r}; "
                    f"expected one of {sorted(kwarg_spec.choices)!r}."
                )
            value = kwarg_spec.choices[value]
        # JSON (and therefore every UI/codegen-supplied override) has no tuple type, so a
        # tuple-typed curated default (e.g. MinMaxScaler's feature_range) always arrives here
        # as a list; sklearn's own param validation rejects a list where it requires a tuple.
        elif isinstance(kwarg_spec.default, tuple) and isinstance(value, list):
            value = tuple(value)
        kwargs[name] = value
    return spec, kwargs


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
    * ``"outlier_detect"`` (unsupervised outlier/novelty detection) ignores ``target`` and
      returns a :class:`FittedModel` with ``task="outlier_detection"`` and ``target=None``.
    * ``"fit_transform"`` (unsupervised transformer) returns a :class:`FittedTransformer`.
      ``target`` is optional here: most transformers (scalers, decomposition, manifold) fit
      unsupervised on features alone, but a curated few (e.g. ``SelectKBest``, ``RFE``,
      ``SelectFromModel``) are supervised feature selectors that need ``y`` to score/rank
      features. When ``target`` is given it is excluded from the resolved feature columns and
      passed as ``y`` to ``.fit``; the fitted transformer itself never needs ``y`` again (its
      later ``.transform(X)`` calls take features only), so ``target`` is not recorded on
      :class:`FittedTransformer`.

    Deterministic given a ``random_state`` kwarg where the underlying estimator accepts one.
    Never mutates ``df``.
    """
    spec, kwargs = _resolve_estimator_and_kwargs(estimator, params)

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

    if spec.archetype == "outlier_detect":
        feature_names = _resolve_features_for_fit(df, features, target=None)
        est = spec.sklearn_class(**kwargs).fit(df[feature_names])
        return FittedModel(
            estimator_type=spec.key,
            task=spec.task or "outlier_detection",
            feature_names=list(feature_names),
            target=None,
            estimator=est,
        )

    # spec.archetype == "fit_transform"
    feature_names = _resolve_features_for_fit(df, features, target=target)
    if target is not None:
        if target not in df.columns:
            raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
        est = spec.sklearn_class(**kwargs).fit(df[feature_names], df[target])
    else:
        est = spec.sklearn_class(**kwargs).fit(df[feature_names])
    return FittedTransformer(
        estimator_type=spec.key,
        feature_names=list(feature_names),
        transformer=est,
    )


@public_op(name="ef.ml.fit_transform")
def fit_transform(
    df: pd.DataFrame,
    *,
    estimator: str,
    target: str | None = None,
    features: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[FittedTransformer, pd.DataFrame]:
    """Fit a curated ``fit_transform``-archetype estimator and transform the SAME frame it fit on.

    The ``ml.fit_transform`` archetype node's backend (Epic 8, Story 5 / ADR 0016). Unlike
    :func:`fit_estimator`'s ``fit_transform`` branch (fit-only), this function calls the
    underlying sklearn transformer's own ``.fit_transform(X[, y])`` in a single step. This
    matters because a few curated transformers (e.g. ``TSNE``) implement ``.fit_transform()``
    but have NO separate ``.transform()`` method at all -- calling ``.fit(X)`` then
    ``.transform(X)`` (what :func:`apply_estimator` does) raises for those even on the training
    data itself. ``.fit_transform()`` is universally supported by every curated transformer (the
    baseline scikit-learn ``TransformerMixin`` contract), so this is the robust way to get both
    the fitted transformer AND its output on one frame in a single node.

    Returns ``(transformer, result)`` where ``result`` is a NEW frame (``df`` is never mutated)
    with added ``component_0``, ``component_1``, ... columns, mirroring
    :func:`apply_estimator`'s ``"transform"`` op column-naming convention. Raises
    :class:`~emergentflow.ml.errors.UnknownEstimatorError` /
    :class:`~emergentflow.ml.errors.InvalidEstimatorParamsError` exactly like
    :func:`fit_estimator`, plus ``ValueError`` if *estimator* is not a ``fit_transform``-
    archetype estimator, or if ``df`` already has any of the output column names.
    """
    spec, kwargs = _resolve_estimator_and_kwargs(estimator, params)
    if spec.archetype != "fit_transform":
        raise ValueError(f"{estimator!r} is not a fit_transform-archetype estimator.")

    feature_names = _resolve_features_for_fit(df, features, target=target)
    est = spec.sklearn_class(**kwargs)
    if target is not None:
        if target not in df.columns:
            raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
        transformed = est.fit_transform(df[feature_names], df[target])
    else:
        transformed = est.fit_transform(df[feature_names])

    if sp.issparse(transformed):
        transformed = transformed.toarray()

    component_cols = [f"component_{i}" for i in range(transformed.shape[1])]
    collisions = [c for c in component_cols if c in df.columns]
    if collisions:
        raise ValueError(f"df already has columns {collisions!r}; rename them before transforming.")

    result = df.copy()
    result[component_cols] = transformed
    transformer = FittedTransformer(
        estimator_type=spec.key,
        feature_names=list(feature_names),
        transformer=est,
    )
    return transformer, result


@public_op(name="ef.ml.select_features")
def select_features(
    df: pd.DataFrame,
    *,
    selector: str,
    target: str | None = None,
    features: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[FittedTransformer, pd.DataFrame, pd.DataFrame]:
    """Fit a curated feature-selector estimator and report which features it kept.

    The ``ml.select_features`` node's backend. Restricted to estimators registered with
    ``EstimatorSpec.is_feature_selector=True`` (``SelectKBest``, ``VarianceThreshold``,
    ``RFE``, ``SelectFromModel``); raises ``ValueError`` for any other estimator key. Some
    curated selectors are supervised (``SelectKBest``, ``RFE``, ``SelectFromModel`` need
    ``target`` to score/rank features); ``VarianceThreshold`` is unsupervised and ignores it.

    Returns ``(selector, result, summary)``:

    * ``selector`` is a :class:`FittedTransformer` (``feature_names`` is the FULL candidate
      column list the selector was fit on, matching :func:`fit_transform`'s convention --
      not just the ones it kept).
    * ``result`` is a NEW frame (``df`` is never mutated): every column NOT among the
      candidate feature columns (e.g. ``target``, id columns) is kept untouched; among the
      candidate feature columns, only the ones the selector selected are kept.
    * ``summary`` is a NEW, tidy DataFrame, one row per candidate feature, with columns
      ``feature`` and ``selected`` (bool, from the fitted selector's ``get_support()`` mask --
      every curated selector implements sklearn's ``SelectorMixin``), plus ``score`` when the
      fitted selector exposes ``scores_`` (e.g. ``SelectKBest``) and/or ``ranking`` when it
      exposes ``ranking_`` (e.g. ``RFE``). Neither extra column is added when the selector
      exposes neither attribute (e.g. ``VarianceThreshold``, ``SelectFromModel``).

    Raises :class:`~emergentflow.ml.errors.UnknownEstimatorError` /
    :class:`~emergentflow.ml.errors.InvalidEstimatorParamsError` exactly like
    :func:`fit_estimator`. Raises ``ValueError`` if *selector* is not a curated feature
    selector, or if ``target`` is given but missing from ``df``.
    """
    spec, kwargs = _resolve_estimator_and_kwargs(selector, params)
    if not spec.is_feature_selector:
        raise ValueError(f"{selector!r} is not a curated feature-selector estimator.")

    feature_names = _resolve_features_for_fit(df, features, target=target)
    est = spec.sklearn_class(**kwargs)
    if target is not None:
        if target not in df.columns:
            raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
        est.fit(df[feature_names], df[target])
    else:
        est.fit(df[feature_names])

    support = est.get_support()
    selected = [f for f, keep in zip(feature_names, support, strict=True) if keep]

    summary = pd.DataFrame({"feature": feature_names, "selected": list(support)})
    if hasattr(est, "scores_"):
        summary["score"] = est.scores_
    if hasattr(est, "ranking_"):
        summary["ranking"] = est.ranking_

    dropped = [f for f in feature_names if f not in selected]
    result = df.drop(columns=dropped)

    transformer = FittedTransformer(
        estimator_type=spec.key, feature_names=list(feature_names), transformer=est
    )
    return transformer, result, summary


@public_op(name="ef.ml.fit_pipeline")
def fit_pipeline(
    df: pd.DataFrame,
    *,
    steps: list[dict[str, Any]],
    target: str | None = None,
    features: list[str] | None = None,
) -> FittedModel:
    """Fit an ordered chain of curated estimators as one sklearn ``Pipeline``.

    The ``ml.pipeline`` node's backend (Epic 8, Story 8 / ADR 0016). Every step but the last
    must be a ``fit_transform``-archetype estimator (a scaler, encoder, decomposition, ...);
    the final step must be a ``fit`` (supervised classifier/regressor), ``cluster_detect``
    (unsupervised label/score), or ``outlier_detect`` (unsupervised outlier/novelty detection)
    archetype estimator. Composing the whole chain into ONE
    ``sklearn.pipeline.Pipeline`` object -- rather than requiring N separate
    ``ml.apply_estimator`` nodes wired in sequence at inference time -- is the distinct
    graph-shape pipelines solve (Epic 8, Story 8): the fitted ``Pipeline`` rides inside a
    single :class:`FittedModel` and, because a ``Pipeline`` duck-types ``.predict()`` /
    ``.transform()`` / ``.score_samples()`` exactly like any single estimator, the EXISTING
    ``ef.ml.apply_estimator`` adapter (and its ``ml.apply_estimator`` node) works against it
    completely unchanged.

    ``steps`` is an ordered list of ``{"estimator": <key>, "params": {...}}`` dicts, each
    validated against the allow-list registry exactly like :func:`fit_estimator` (unknown
    estimator/params raise the same typed errors:
    :class:`~emergentflow.ml.errors.UnknownEstimatorError` /
    :class:`~emergentflow.ml.errors.InvalidEstimatorParamsError`). Raises ``ValueError`` if
    ``steps`` is empty, if any non-final step is not a ``fit_transform``-archetype estimator,
    or if the final step is not a ``fit``/``cluster_detect``/``outlier_detect``-archetype
    estimator. A ``fit`` final step requires ``target`` (mirroring :func:`fit_estimator`);
    ``cluster_detect`` and ``outlier_detect`` final steps ignore ``target`` entirely.

    Deterministic given a ``random_state`` kwarg where the underlying estimators accept one.
    Never mutates ``df``.
    """
    if not steps:
        raise ValueError("pipeline requires at least one step.")

    *transform_steps, final_step = steps
    sk_steps: list[tuple[str, Any]] = []
    for i, step in enumerate(transform_steps):
        spec, kwargs = _resolve_estimator_and_kwargs(step["estimator"], step.get("params"))
        if spec.archetype != "fit_transform":
            raise ValueError(
                f"pipeline step {step['estimator']!r} must be a fit_transform-archetype "
                "estimator (every step except the last)."
            )
        sk_steps.append((f"{i}_{step['estimator']}", spec.sklearn_class(**kwargs)))

    final_spec, final_kwargs = _resolve_estimator_and_kwargs(
        final_step["estimator"], final_step.get("params")
    )
    if final_spec.archetype not in ("fit", "cluster_detect", "outlier_detect"):
        raise ValueError(
            f"pipeline's final step {final_step['estimator']!r} must be a fit, "
            "cluster_detect, or outlier_detect-archetype estimator."
        )
    sk_steps.append(
        (
            f"{len(transform_steps)}_{final_step['estimator']}",
            final_spec.sklearn_class(**final_kwargs),
        )
    )
    pipe = _SkPipeline(sk_steps)

    if final_spec.archetype == "fit":
        if target is None:
            raise ValueError(
                f"pipeline estimator {final_step['estimator']!r} requires a target column."
            )
        if target not in df.columns:
            raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")
        feature_names = _resolve_features_for_fit(df, features, target=target)
        pipe.fit(df[feature_names], df[target])
        return FittedModel(
            estimator_type="Pipeline",
            task=final_spec.task or "classification",
            feature_names=list(feature_names),
            target=target,
            estimator=pipe,
        )

    # final_spec.archetype in ("cluster_detect", "outlier_detect")
    feature_names = _resolve_features_for_fit(df, features, target=None)
    pipe.fit(df[feature_names])
    return FittedModel(
        estimator_type="Pipeline",
        task=final_spec.task
        or ("outlier_detection" if final_spec.archetype == "outlier_detect" else "clustering"),
        feature_names=list(feature_names),
        target=None,
        estimator=pipe,
    )


@public_op(name="ef.ml.grid_search")
def grid_search(
    df: pd.DataFrame,
    *,
    estimator: str,
    param_grid: dict[str, list[Any]],
    target: str,
    features: list[str] | None = None,
    cv: int = 5,
    scoring: str | None = None,
) -> tuple[FittedModel, pd.DataFrame]:
    """Search ``param_grid`` for a curated, ``fit``-archetype (supervised) estimator.

    The ``ml.grid_search`` node's backend (Epic 8, Story 8 / ADR 0016). Thin wrapper over
    ``sklearn.model_selection.GridSearchCV``: fits every combination of ``param_grid`` values
    via ``cv``-fold cross-validation and refits the best-scoring combination on the full
    ``df``. Restricted to ``fit``-archetype estimators (classifiers/regressors) -- clustering
    and transformer archetypes are out of scope for this node.

    ``param_grid`` keys are validated against the estimator's ``accepted_kwargs`` allow-list
    (unknown keys raise :class:`~emergentflow.ml.errors.InvalidEstimatorParamsError`), exactly
    like every other adapter entry point; each value must be a non-empty list of candidate
    values for that kwarg. Raises ``ValueError`` if *estimator* is not a ``fit``-archetype
    estimator, if ``param_grid`` is empty, or if ``target`` is missing from ``df``.

    Returns ``(model, cv_results)`` where ``model`` is a :class:`FittedModel` wrapping
    ``GridSearchCV.best_estimator_`` (a real fitted instance of the estimator's own sklearn
    class, refit on all of ``df`` -- so ``ef.ml.evaluate``/``ef.ml.summarize`` work on it
    exactly as they would on a directly-fit estimator) and ``cv_results`` is a NEW, tidy
    DataFrame (one row per parameter combination, sorted by rank) with one ``param_<name>``
    column per searched kwarg plus ``mean_test_score``, ``std_test_score``, ``rank_test_score``,
    and ``mean_fit_time``. ``df`` is never mutated.
    """
    spec, base_kwargs = _resolve_estimator_and_kwargs(estimator, None)
    if spec.archetype != "fit":
        raise ValueError(
            f"{estimator!r} is not a fit-archetype estimator; grid_search requires a "
            "supervised classifier/regressor."
        )
    if not param_grid:
        raise ValueError("param_grid must not be empty.")
    unknown_params = [k for k in param_grid if k not in spec.accepted_kwargs]
    if unknown_params:
        raise InvalidEstimatorParamsError(
            f"unknown params {unknown_params!r} for estimator {estimator!r}; "
            f"expected one of {sorted(spec.accepted_kwargs)!r}."
        )
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    feature_names = _resolve_features_for_fit(df, features, target=target)
    grid = GridSearchCV(
        spec.sklearn_class(**base_kwargs), param_grid=param_grid, cv=cv, scoring=scoring
    )
    grid.fit(df[feature_names], df[target])

    model = FittedModel(
        estimator_type=spec.key,
        task=spec.task or "classification",
        feature_names=list(feature_names),
        target=target,
        estimator=grid.best_estimator_,
    )

    cv_results = grid.cv_results_
    result_df = pd.DataFrame(
        {f"param_{name}": list(cv_results[f"param_{name}"]) for name in sorted(param_grid)}
    )
    result_df["mean_test_score"] = cv_results["mean_test_score"]
    result_df["std_test_score"] = cv_results["std_test_score"]
    result_df["rank_test_score"] = cv_results["rank_test_score"]
    result_df["mean_fit_time"] = cv_results["mean_fit_time"]
    result_df = result_df.sort_values("rank_test_score").reset_index(drop=True)

    return model, result_df


@public_op(name="ef.ml.tune_model")
def tune_model(
    df: pd.DataFrame,
    *,
    estimator: str,
    param_distributions: dict[str, list[Any]],
    target: str,
    features: list[str] | None = None,
    n_iter: int = 10,
    cv: int = 5,
    scoring: str | None = None,
    random_state: int = 0,
) -> tuple[FittedModel, pd.DataFrame]:
    """Randomized hyperparameter search over a curated, ``fit``-archetype (supervised) estimator.

    The ``ml.tune_model`` node's backend (Epic 8, Story 8 / ADR 0016). Thin wrapper over
    ``sklearn.model_selection.RandomizedSearchCV``: samples ``n_iter`` combinations from
    ``param_distributions`` via ``cv``-fold cross-validation and refits the best-scoring
    combination on the full ``df``. Restricted to ``fit``-archetype estimators
    (classifiers/regressors) -- clustering and transformer archetypes are out of scope for this
    node.

    ``param_distributions`` keys are validated against the estimator's ``accepted_kwargs``
    allow-list (unknown keys raise
    :class:`~emergentflow.ml.errors.InvalidEstimatorParamsError`), exactly like every other
    adapter entry point; each value must be a non-empty list of candidate values for that kwarg.
    Raises ``ValueError`` if *estimator* is not a ``fit``-archetype estimator, if
    ``param_distributions`` is empty, or if ``target`` is missing from ``df``.

    Returns ``(model, cv_results)`` where ``model`` is a :class:`FittedModel` wrapping
    ``RandomizedSearchCV.best_estimator_`` (a real fitted instance of the estimator's own sklearn
    class, refit on all of ``df`` -- so ``ef.ml.evaluate``/``ef.ml.summarize`` work on it
    exactly as they would on a directly-fit estimator) and ``cv_results`` is a NEW, tidy
    DataFrame (one row per sampled parameter combination, sorted by rank) with one
    ``param_<name>`` column per searched kwarg plus ``mean_test_score``, ``std_test_score``,
    ``rank_test_score``, and ``mean_fit_time``. ``df`` is never mutated.
    """
    spec, base_kwargs = _resolve_estimator_and_kwargs(estimator, None)
    if spec.archetype != "fit":
        raise ValueError(
            f"{estimator!r} is not a fit-archetype estimator; tune_model requires a "
            "supervised classifier/regressor."
        )
    if not param_distributions:
        raise ValueError("param_distributions must not be empty.")
    unknown_params = [k for k in param_distributions if k not in spec.accepted_kwargs]
    if unknown_params:
        raise InvalidEstimatorParamsError(
            f"unknown params {unknown_params!r} for estimator {estimator!r}; "
            f"expected one of {sorted(spec.accepted_kwargs)!r}."
        )
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    feature_names = _resolve_features_for_fit(df, features, target=target)
    grid = RandomizedSearchCV(
        spec.sklearn_class(**base_kwargs),
        param_distributions=param_distributions,
        n_iter=n_iter,
        cv=cv,
        scoring=scoring,
        random_state=random_state,
    )
    grid.fit(df[feature_names], df[target])

    model = FittedModel(
        estimator_type=spec.key,
        task=spec.task or "classification",
        feature_names=list(feature_names),
        target=target,
        estimator=grid.best_estimator_,
    )

    cv_results = grid.cv_results_
    result_df = pd.DataFrame(
        {f"param_{name}": list(cv_results[f"param_{name}"]) for name in sorted(param_distributions)}
    )
    result_df["mean_test_score"] = cv_results["mean_test_score"]
    result_df["std_test_score"] = cv_results["std_test_score"]
    result_df["rank_test_score"] = cv_results["rank_test_score"]
    result_df["mean_fit_time"] = cv_results["mean_fit_time"]
    result_df = result_df.sort_values("rank_test_score").reset_index(drop=True)

    return model, result_df


@public_op(name="ef.ml.cross_validate")
def cross_validate(
    df: pd.DataFrame,
    *,
    estimator: str,
    target: str,
    features: list[str] | None = None,
    params: dict[str, Any] | None = None,
    cv: int = 5,
    scoring: str | None = None,
) -> pd.DataFrame:
    """Cross-validate a curated, ``fit``-archetype (supervised) estimator on ``df``.

    The ``ml.cross_validate`` node's backend (Epic 8, Story 8 / ADR 0016). Thin wrapper over
    ``sklearn.model_selection.cross_validate``: fits and scores ``cv`` folds of a single,
    fixed-hyperparameter estimator instance. Unlike :func:`grid_search`, this produces no
    reusable :class:`FittedModel` -- sklearn's ``cross_validate`` fits and discards its
    internal per-fold models by default and has no single canonical "best" estimator to keep,
    so this is a pure evaluation step.

    ``estimator``/``params`` are validated against the allow-list registry exactly like
    :func:`fit_estimator` (unknown estimator/params raise the same typed errors). Raises
    ``ValueError`` if *estimator* is not a ``fit``-archetype estimator or if ``target`` is
    missing from ``df``.

    Returns a NEW, tidy DataFrame, one row per fold, with columns ``fold`` (0-indexed),
    ``test_score``, ``fit_time``, ``score_time``. ``df`` is never mutated.
    """
    spec, kwargs = _resolve_estimator_and_kwargs(estimator, params)
    if spec.archetype != "fit":
        raise ValueError(
            f"{estimator!r} is not a fit-archetype estimator; cross_validate requires a "
            "supervised classifier/regressor."
        )
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    feature_names = _resolve_features_for_fit(df, features, target=target)
    est = spec.sklearn_class(**kwargs)
    cv_result = _sk_cross_validate(est, df[feature_names], df[target], cv=cv, scoring=scoring)

    return pd.DataFrame(
        {
            "fold": list(range(len(cv_result["test_score"]))),
            "test_score": cv_result["test_score"],
            "fit_time": cv_result["fit_time"],
            "score_time": cv_result["score_time"],
        }
    )


@public_op(name="ef.ml.compare_models")
def compare_models(
    df: pd.DataFrame,
    *,
    task: str,
    target: str,
    features: list[str] | None = None,
    estimators: list[str] | None = None,
    cv: int = 5,
    sort_by: str | None = None,
) -> tuple[pd.DataFrame, FittedModel]:
    """Cross-validate every curated fit-archetype estimator matching *task* and rank them.

    The ``ml.compare_models`` node's backend: a PyCaret-style "run every curated baseline
    model and see which wins" step. Cross-validates each candidate estimator (curated
    defaults only -- no per-estimator hyperparameter overrides; use ``ml.grid_search`` on the
    winner for that) via ``sklearn.model_selection.cross_validate`` with a fixed,
    task-appropriate set of scoring metrics, computed in one pass per estimator (sklearn's
    ``cross_validate`` accepts a list of scorer names directly).

    ``task="classification"`` scores ``accuracy`` and ``f1`` (weighted, safe for binary and
    multiclass alike) always, plus ``roc_auc`` only when ``target`` has exactly two distinct
    values (sklearn's ``roc_auc`` scorer raises for multiclass targets, so it is omitted
    rather than attempted-and-failed for a >2-class target). ``task="regression"`` scores
    ``r2``, ``mae``, ``rmse``. ``estimators`` defaults to every curated ``fit``-archetype
    estimator whose registered ``task`` matches; passing an explicit list restricts (and
    validates against) that set -- every key must be a ``fit``-archetype estimator whose
    ``task`` matches *task*, or this raises ``ValueError``.

    Prints a ``tqdm`` progress bar to stderr over the per-estimator loop -- a deliberate,
    narrowly-scoped exception to this module's usual purity: the bar is pure console/log
    output, never touches the return value, filesystem, or network, and behaves identically
    whether this function is called via ``execute()`` or from the compiled script's
    ``ef.ml.compare_models(...)`` call (ADR-0002 equivalence holds on the RESULT either way).

    Returns ``(comparison, best_model)``:

    * ``comparison`` is a NEW, tidy DataFrame, one row per candidate estimator, with an
      ``estimator`` column, a ``status`` column (``"ok"``, or the first line of the exception
      message when an estimator is fundamentally incompatible with this data -- e.g.
      ``MultinomialNB`` on negative features -- so one bad-fit candidate degrades to a NaN row
      instead of aborting the whole comparison), one column per scoring metric (mean across
      folds, NaN for a failed row), and ``fit_time`` (mean fit seconds per fold), sorted by
      ``sort_by`` (or the task's default: ``"accuracy"`` for classification, ``"r2"`` for
      regression) -- descending for higher-is-better metrics (accuracy/f1/roc_auc/r2),
      ascending for lower-is-better metrics (mae/rmse); failed (NaN) rows always sort last.
    * ``best_model`` is a :class:`FittedModel` wrapping the top-ranked estimator among the
      ones that actually fit, refit on the FULL ``df`` (mirrors :func:`grid_search`'s
      refit-on-full-data convention) -- directly usable with
      :func:`evaluate`/:func:`apply_estimator`.

    Raises ``ValueError`` if *task* is not one of ``FOREST_TASKS``, if ``target`` is missing
    from ``df``, if no candidate estimators exist for *task*, if any explicit ``estimators``
    entry is not a ``fit``-archetype estimator matching *task*, if ``sort_by`` is not one of
    the task's scoring metric names, or if every candidate estimator failed to fit. ``df`` is
    never mutated.
    """
    if task not in FOREST_TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {list(FOREST_TASKS)!r}.")
    if target not in df.columns:
        raise ValueError(f"unknown target {target!r}; expected one of {list(df.columns)!r}.")

    candidate_keys = (
        estimators
        if estimators is not None
        else [k for k in keys_for_archetype("fit") if get_estimator_spec(k).task == task]
    )
    if not candidate_keys:
        raise ValueError(f"no curated estimators to compare for task {task!r}.")
    for key in candidate_keys:
        candidate_spec = get_estimator_spec(key)
        if candidate_spec.archetype != "fit":
            raise ValueError(f"{key!r} is not a fit-archetype estimator.")
        if candidate_spec.task != task:
            raise ValueError(f"{key!r} is a {candidate_spec.task!r} estimator; expected {task!r}.")

    feature_names = _resolve_features_for_fit(df, features, target=target)
    X = df[feature_names]
    y = df[target]

    if task == "classification":
        scoring = {"accuracy": "accuracy", "f1": "f1_weighted"}
        if y.nunique() == 2:
            scoring["roc_auc"] = "roc_auc"
        higher_is_better = {"accuracy": True, "f1": True, "roc_auc": True}
        default_sort = "accuracy"
    else:
        scoring = {
            "r2": "r2",
            "mae": "neg_mean_absolute_error",
            "rmse": "neg_root_mean_squared_error",
        }
        higher_is_better = {"r2": True, "mae": False, "rmse": False}
        default_sort = "r2"

    sort_metric = sort_by or default_sort
    if sort_metric not in scoring:
        raise ValueError(f"sort_by {sort_metric!r} must be one of {sorted(scoring)!r}.")

    rows: list[dict[str, Any]] = []
    for key in tqdm(candidate_keys, desc="Comparing models", file=sys.stderr):
        row_spec, row_kwargs = _resolve_estimator_and_kwargs(key, None)
        est = row_spec.sklearn_class(**row_kwargs)
        row: dict[str, Any] = {"estimator": key, "status": "ok"}
        try:
            cv_result = _sk_cross_validate(est, X, y, cv=cv, scoring=list(scoring.values()))
        except Exception as exc:  # noqa: BLE001 -- one incompatible curated estimator (e.g.
            # MultinomialNB on negative features) must not abort comparing the rest; its row
            # is marked failed instead, mirroring how sklearn's own cross_validate already
            # degrades a PARTIAL fold failure to NaN rather than raising.
            row["status"] = (str(exc).strip().splitlines() or ["Unknown error"])[0][:200]
            for metric_name in scoring:
                row[metric_name] = float("nan")
            row["fit_time"] = float("nan")
            rows.append(row)
            continue
        for metric_name, sk_scorer_name in scoring.items():
            mean_score = float(cv_result[f"test_{sk_scorer_name}"].mean())
            if sk_scorer_name.startswith("neg_"):
                mean_score = -mean_score
            row[metric_name] = mean_score
        row["fit_time"] = float(cv_result["fit_time"].mean())
        rows.append(row)

    comparison = (
        pd.DataFrame(rows)
        .sort_values(sort_metric, ascending=not higher_is_better[sort_metric], na_position="last")
        .reset_index(drop=True)
    )

    fit_rows = comparison[comparison["status"] == "ok"]
    if fit_rows.empty:
        raise ValueError(
            f"every candidate estimator failed to fit for task {task!r}; see the "
            "'status' column for details."
        )

    best_key = cast(str, fit_rows.iloc[0]["estimator"])
    best_spec, best_kwargs = _resolve_estimator_and_kwargs(best_key, None)
    best_estimator = best_spec.sklearn_class(**best_kwargs).fit(X, y)
    best_model = FittedModel(
        estimator_type=best_key,
        task=task,
        feature_names=list(feature_names),
        target=target,
        estimator=best_estimator,
    )

    return comparison, best_model


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

    * ``"predict"`` requires a :class:`FittedModel` (``fit``, ``cluster_detect``, or
      ``outlier_detect`` archetype) and adds a ``prediction`` column, mirroring :func:`predict`.
      For ``outlier_detect`` models this produces ``-1``/``1`` outlier labels.
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


@public_op(name="ef.ml.fit_and_label")
def fit_and_label(
    df: pd.DataFrame,
    *,
    estimator: str,
    features: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[FittedModel, pd.DataFrame]:
    """Fit a curated ``cluster_detect``-archetype estimator and label the SAME frame it fit on.

    The ``cluster_detect`` archetype's backend (Epic 8, Story 6 / ADR 0016): unlike the ``fit``
    archetype (fit now, predict on new data later via a separate ``ml.apply_estimator`` node),
    clustering/mixture/outlier estimators produce their labels/scores as part of fitting itself,
    and some (``DBSCAN``, ``AgglomerativeClustering``, ``SpectralClustering``) never support
    predicting on new data at all -- sklearn only ever gives you ``.labels_`` computed at fit
    time for those. So this function fits via :func:`fit_estimator` and immediately labels the
    *same* input frame, preferring the fitted ``.labels_`` attribute (present for every true
    clustering estimator) and falling back to ``.predict(X)`` on the training data itself
    (mixture models and outlier/novelty detectors, which don't set ``.labels_``).

    Deliberately does NOT fall back to ``.labels_`` inside ``ml.apply_estimator``'s existing
    ``"predict"`` op: that op is used to predict on a *different*, later frame, and replaying
    stale training-time labels there regardless of the new frame's rows would be a silent
    correctness bug, not a graceful fallback. A ``labels_``-only estimator (e.g. ``DBSCAN``)
    correctly still raises ``ValueError`` there ("does not support predict") -- the disabled-not-
    surprising behavior the archetype requires for estimators with no reusable predictor.

    Returns ``(model, labeled_df)`` where ``labeled_df`` is a NEW frame (``df`` is never
    mutated) with an added ``"cluster"`` column (used uniformly for clustering, mixture, and
    outlier/novelty families alike -- continuous anomaly scores remain available separately via
    the existing ``ml.apply_estimator`` node's ``"score_samples"`` op for estimators that support
    it). Raises ``ValueError`` if *estimator* is not a ``cluster_detect``-archetype estimator, if
    ``df`` already has a ``"cluster"`` column, or if the fitted estimator exposes none of
    ``.labels_``, ``.predict``, ``.fit_predict`` (the last covers ``LocalOutlierFactor`` with
    ``novelty=False``, whose ``.predict`` is only available when ``novelty=True``).
    """
    spec = get_estimator_spec(estimator)
    if spec.archetype != "cluster_detect":
        raise ValueError(f"{estimator!r} is not a cluster_detect-archetype estimator.")
    if "cluster" in df.columns:
        raise ValueError("df already has a 'cluster' column; rename it before labeling.")
    # spec.archetype == "cluster_detect" guarantees fit_estimator returns a FittedModel.
    fitted = fit_estimator(df, estimator=estimator, features=features, params=params)
    model = cast(FittedModel, fitted)
    est = model.estimator
    if hasattr(est, "labels_"):
        labels = est.labels_
    elif hasattr(est, "predict"):
        labels = est.predict(df[model.feature_names])
    elif hasattr(est, "fit_predict"):
        labels = est.fit_predict(df[model.feature_names])
    else:
        raise ValueError(f"{model.estimator_type} exposes neither labels_ nor predict.")
    result = df.copy()
    result["cluster"] = labels
    return model, result


@public_op(name="ef.ml.fit_and_detect")
def fit_and_detect(
    df: pd.DataFrame,
    *,
    estimator: str,
    features: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[FittedModel, pd.DataFrame]:
    """Fit a curated ``outlier_detect``-archetype estimator and label the SAME frame it fit on.

    The ``ml.outlier_detect`` archetype's backend (Epic 8, Story 6 / ADR 0016). Outlier and
    novelty detectors produce their labels as part of fitting itself. This function fits via
    :func:`fit_estimator` and immediately labels the *same* input frame, which constrains how
    the labels may be obtained -- in priority order:

    * ``LocalOutlierFactor`` is read from its fit-time ``negative_outlier_factor_`` /
      ``offset_`` attributes. sklearn documents that with ``novelty=True`` (the curated
      default, needed so a later ``ml.apply_estimator`` can predict on a *different* frame)
      you "should only use predict, decision_function and score_samples on new unseen data
      and not on the training set" -- self-scoring finds each point as its own nearest
      neighbor at distance 0 and inflates its local density, silently misclassifying points
      near the boundary. The fit-time attributes ARE the standard LOF labels for the fitted
      frame, so this path is both correct and independent of ``novelty``.
    * Otherwise ``.predict(X)`` when available (``IsolationForest``, ``OneClassSVM``,
      ``EllipticEnvelope``, whose training-set predictions are well-defined).
    * Otherwise ``.fit_predict(X)``.

    Returns ``(model, labeled_df)`` where ``labeled_df`` is a NEW frame (``df`` is never
    mutated) with an added ``"outlier"`` column following sklearn's convention (``-1`` for
    outliers, ``1`` for inliers). Raises ``ValueError`` if *estimator* is not an
    ``outlier_detect``-archetype estimator, if ``df`` already has an ``"outlier"`` column, or
    if the fitted estimator exposes neither ``.predict`` nor ``.fit_predict``.
    """
    spec = get_estimator_spec(estimator)
    if spec.archetype != "outlier_detect":
        raise ValueError(f"{estimator!r} is not an outlier_detect-archetype estimator.")
    if "outlier" in df.columns:
        raise ValueError("df already has an 'outlier' column; rename it before detecting.")
    # spec.archetype == "outlier_detect" guarantees fit_estimator returns a FittedModel.
    fitted = fit_estimator(df, estimator=estimator, features=features, params=params)
    model = cast(FittedModel, fitted)
    est = model.estimator
    X = df[model.feature_names]
    negative_outlier_factor = getattr(est, "negative_outlier_factor_", None)
    if negative_outlier_factor is not None:
        # LocalOutlierFactor -- see the docstring: .predict() on the fitted frame is the one
        # usage sklearn rules out, and these attributes give the standard LOF labels instead.
        labels = np.where(negative_outlier_factor < est.offset_, -1, 1)
    elif hasattr(est, "predict"):
        labels = est.predict(X)
    elif hasattr(est, "fit_predict"):
        labels = est.fit_predict(X)
    else:
        raise ValueError(f"{model.estimator_type} exposes neither predict nor fit_predict.")
    result = df.copy()
    result["outlier"] = labels
    return model, result


@dataclass
class DimensionReductionResult:
    """Structured, inspectable result of a dimensionality reduction.

    Attributes
    ----------
    coordinates: a COPY of the input DataFrame with ``n_components`` new columns
        (``component_1``, ``component_2``, ...) appended.
    method: ``"pca"``, ``"tsne"``, or ``"umap"``.
    n_components: how many reduced dimensions were produced.
    seed: the random seed used (captured for reproducibility).
    explained_variance: for ``method="pca"`` only, a tidy DataFrame with columns
        ``component``/``explained_variance_ratio``/``cumulative_variance_ratio``. ``None`` for
        ``"tsne"``/``"umap"`` (neither method produces a variance-explained decomposition).
    """

    coordinates: pd.DataFrame
    method: str
    n_components: int
    seed: int
    explained_variance: pd.DataFrame | None = None


_REDUCE_DIM_METHODS = ("pca", "tsne", "umap")


@public_op(name="ef.ml.reduce_dimensions")
def reduce_dimensions(
    df: pd.DataFrame,
    *,
    feature_cols: list[str],
    method: str = "pca",
    n_components: int = 2,
    seed: int = 0,
) -> DimensionReductionResult:
    """Reduce ``feature_cols`` to ``n_components`` new coordinate columns via PCA/t-SNE/UMAP.

    PCA (``sklearn.decomposition.PCA``) and t-SNE (``sklearn.manifold.TSNE``) run on hard deps
    (scikit-learn is already a hard dependency of this SDK); UMAP (``umap-learn``) is
    lazy-imported behind the optional ``[umap]`` extra, raising a typed
    ``MissingOptionalDependencyError`` if absent -- checked BEFORE any ``umap`` import and before
    the rest of the computation runs. Appends ``component_1``..``component_<n_components>`` to a
    COPY of ``df`` (never mutates ``df``), guarding against a column-name collision with a typed
    ``ValueError``. ``seed`` is captured for reproducibility, threaded into each method's
    ``random_state``. PCA additionally returns a tidy explained-variance frame.
    """
    if method not in _REDUCE_DIM_METHODS:
        raise ValueError(
            f"unknown method {method!r}; expected one of {list(_REDUCE_DIM_METHODS)!r}."
        )
    unknown = [c for c in feature_cols if c not in df.columns]
    if unknown:
        raise ValueError(f"unknown feature_cols {unknown!r}; expected one of {list(df.columns)!r}.")
    if n_components < 1:
        raise ValueError(f"n_components must be >= 1; got {n_components}.")
    new_cols = [f"component_{i + 1}" for i in range(n_components)]
    collisions = [c for c in new_cols if c in df.columns]
    if collisions:
        raise ValueError(
            f"reduce_dimensions would overwrite existing column(s) {collisions!r}; "
            f"rename them before calling."
        )
    x = df[feature_cols].to_numpy()
    explained_variance: pd.DataFrame | None = None
    if method == "pca":
        from sklearn.decomposition import PCA

        model = PCA(n_components=n_components, random_state=seed)
        coords = model.fit_transform(x)
        ratios = model.explained_variance_ratio_
        explained_variance = pd.DataFrame(
            {
                "component": new_cols,
                "explained_variance_ratio": ratios,
                "cumulative_variance_ratio": ratios.cumsum(),
            }
        )
    elif method == "tsne":
        from sklearn.manifold import TSNE

        model = TSNE(n_components=n_components, random_state=seed)
        coords = model.fit_transform(x)
    else:
        if importlib.util.find_spec("umap") is None:
            raise MissingOptionalDependencyError("emergentflow[umap]")
        from umap import UMAP

        model = UMAP(n_components=n_components, random_state=seed)
        coords = model.fit_transform(x)
    result_df = df.copy()
    for i, col in enumerate(new_cols):
        result_df[col] = coords[:, i]
    return DimensionReductionResult(
        coordinates=result_df,
        method=method,
        n_components=n_components,
        seed=seed,
        explained_variance=explained_variance,
    )


@public_op(name="ef.ml.save_model")
def save_model(
    model: FittedModel | FittedTransformer,
    path: str | Path,
) -> ArtifactRef:
    """Serialize *model* to *path* using joblib and return an ArtifactRef.

    Writes two files:
      - ``<path>`` — the pickled model (via joblib).
      - ``<path>.meta.json`` — a sidecar with sdk version, sklearn version,
        estimator type, task, feature names, and target.

    The sidecar enables ``load_model`` to version-check before deserializing.
    Documented as unsandboxed deserialization (same trust model as
    ``ExecutionCache`` / ``ArtifactStore``): loading a pickle is code execution.

    Parameters
    ----------
    model:
        The fitted model or transformer to save.
    path:
        Destination file path (e.g. ``"models/churn_rf_v3.joblib"``).
        Parent directories are created if missing.

    Returns
    -------
    ArtifactRef
        A reference to the saved artifact with ``uri=str(path)`` and
        ``media_type="application/octet-stream"``.

    Raises
    ------
    ModelPersistenceError
        If *model* is not a :class:`FittedModel` or :class:`FittedTransformer`.
    """
    if not isinstance(model, (FittedModel, FittedTransformer)):
        raise ModelPersistenceError(
            f"save_model expects a FittedModel or FittedTransformer; got {type(model).__name__}."
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    import sklearn

    joblib.dump(model, path)

    meta = {
        "sdk_version": __version__,
        "sklearn_version": sklearn.__version__,
        "estimator_type": model.estimator_type,
        "task": getattr(model, "task", None),
        "feature_names": model.feature_names,
        "target": getattr(model, "target", None),
        "timestamp": time.time(),
    }
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return ArtifactRef(uri=str(path), media_type="application/octet-stream")


@public_op(name="ef.ml.load_model")
def load_model(
    ref_or_path: str | Path | ArtifactRef,
) -> FittedModel | FittedTransformer:
    """Deserialize a saved model from *ref_or_path*.

    Validates the sidecar's sklearn version against the current environment
    and raises :class:`ModelPersistenceError` on mismatch with a clear
    explanatory message instead of an opaque unpickling failure.

    Parameters
    ----------
    ref_or_path:
        An ``ArtifactRef``, a file path string, or a ``Path``. When an
        ``ArtifactRef`` is passed, its ``uri`` is used as the path.

    Returns
    -------
    FittedModel | FittedTransformer
        The deserialized model.

    Raises
    ------
    ModelPersistenceError
        If the sidecar's sklearn version does not match the current
        environment's sklearn version, or if the loaded object is not a
        FittedModel / FittedTransformer.
    FileNotFoundError
        If the model file does not exist.
    """
    import sklearn

    path = Path(ref_or_path.uri) if isinstance(ref_or_path, ArtifactRef) else Path(ref_or_path)

    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")

    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        saved_sklearn_version = meta.get("sklearn_version")
        current_sklearn_version = sklearn.__version__
        if saved_sklearn_version and saved_sklearn_version != current_sklearn_version:
            raise ModelPersistenceError(
                f"Model was saved with sklearn v{saved_sklearn_version} but the current "
                f"environment has sklearn v{current_sklearn_version}. "
                f"Install the matching version: `pip install scikit-learn=={saved_sklearn_version}`"
            )
    else:
        # No sidecar: allow loading for backward compatibility with models saved
        # before the sidecar was introduced, but warn that no version check ran.
        warnings.warn(
            f"Model at {path} has no {path.name}.meta.json sidecar; "
            "skipping the sklearn version check.",
            stacklevel=2,
        )

    model = joblib.load(path)
    if not isinstance(model, (FittedModel, FittedTransformer)):
        raise ModelPersistenceError(
            f"Loaded object is not a FittedModel or FittedTransformer; got {type(model).__name__}."
        )
    return model


# Importing the seed catalog registers its estimator allow-list entries (LogisticRegression,
# StandardScaler, KMeans, GaussianMixture) into the registry the moment ``emergentflow.ml`` is
# imported — the same import-for-side-effect pattern ``emergentflow.types`` uses for its type
# catalog. Kept last so ``fit_estimator``/``get_estimator_spec`` are fully defined first. The
# lint suppression marks it as not-at-top (E402) and unused-but-intentional (F401).
from emergentflow.ml import catalog  # noqa: E402, F401
