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

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split as _sk_split

from emergentflow.api import public_op

__all__ = [
    "FOREST_TASKS",
    "evaluate",
    "predict",
    "train_classifier",
    "train_random_forest",
    "train_regressor",
    "train_test_split",
    "ClassifierResult",
    "EvaluationResult",
    "FittedModel",
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
    """

    estimator_type: str  # e.g. "LinearRegression", "RandomForestClassifier"
    task: str  # "classification" | "regression"
    feature_names: list[str]
    target: str
    estimator: Any  # live sklearn estimator; not JSON-serialized


@dataclass
class EvaluationResult:
    """Inspectable evaluation metrics for a fitted model on a dataset."""

    task: str
    n: int
    metrics: dict[str, float]


@public_op(name="ef.ml.evaluate")
def evaluate(model: FittedModel, df: pd.DataFrame) -> EvaluationResult:
    """Score a fitted model against the true ``model.target`` in ``df``.

    Regression metrics: ``r2``, ``mae``, ``rmse``. Classification metric: ``accuracy``. Validates
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
    return EvaluationResult(task=model.task, n=int(df.shape[0]), metrics=metrics)


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
