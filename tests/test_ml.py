"""Tests for ``colonymind.ml`` (Epic 1, Story 8).

Covers ``cm.ml.train_classifier``: a thin wrapper over
``sklearn.linear_model.LogisticRegression`` that trains a classifier and
returns inspectable metrics (never the fitted estimator itself, per Story 7
rule 4).
"""

from __future__ import annotations

import pandas as pd
import pytest

from colonymind.api import PUBLIC_OPS
from colonymind.ml import ClassifierResult, train_classifier


def _make_df() -> pd.DataFrame:
    """A small, linearly separable 2-class dataset (40 rows).

    ``label`` is fully determined by a threshold on ``x1 + x2``, so the
    classifier should achieve high, stable accuracy regardless of which rows
    land in the train/test split.
    """
    x1 = [float(i) for i in range(20)] + [float(i) for i in range(20)]
    x2 = [float(i % 5) for i in range(40)]
    label = ["low" if (a + b) < 15 else "high" for a, b in zip(x1, x2, strict=True)]
    return pd.DataFrame({"x1": x1, "x2": x2, "label": label})


def test_train_returns_result() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert isinstance(result, ClassifierResult)
    # Must not be (or expose) the opaque sklearn estimator (Story 7 rule 4).
    assert not hasattr(result, "predict")


def test_train_accuracy_in_range() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert 0.0 <= result.accuracy <= 1.0


def test_train_counts_sum_to_total() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert result.n_train + result.n_test == len(df)


def test_train_classes_and_coefficients() -> None:
    df = _make_df()
    result = train_classifier(df, target="label", random_state=0)
    assert len(result.classes) == 2
    assert isinstance(result.coefficients, list)
    assert len(result.coefficients) > 0
    for row in result.coefficients:
        assert isinstance(row, list)
        assert len(row) == len(result.feature_names)
        for value in row:
            assert isinstance(value, float)


def test_train_deterministic() -> None:
    df = _make_df()
    first = train_classifier(df, target="label", random_state=0)
    second = train_classifier(df, target="label", random_state=0)
    assert first.accuracy == second.accuracy
    assert first.coefficients == second.coefficients


def test_train_does_not_mutate_input() -> None:
    df = _make_df()
    original = df.copy()
    train_classifier(df, target="label", random_state=0)
    assert df.equals(original)


def test_train_missing_target_raises() -> None:
    df = _make_df()
    with pytest.raises(ValueError):
        train_classifier(df, target="bogus", random_state=0)


def test_train_registered_as_public_op() -> None:
    assert "cm.ml.train_classifier" in PUBLIC_OPS
