"""
colonymind.ml
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

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from colonymind.api import public_op

__all__ = ["train_classifier", "ClassifierResult"]


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


@public_op(name="cm.ml.train_classifier")
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

    X_train, X_test, y_train, y_test = train_test_split(
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
