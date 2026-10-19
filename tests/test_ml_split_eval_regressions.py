"""Regression tests: temporal split float truncation and string-label evaluate metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

import emergentflow as ef


def test_temporal_split_test_size_not_truncated_by_float_noise() -> None:
    # 10 * (1 - 0.8) == 1.9999999999999996 -> int() gave a 1-row train / 9-row test.
    df = pd.DataFrame({"t": range(10), "x": range(10)})
    train, test = ef.ml.train_test_split(df, strategy="temporal", time_col="t", test_size=0.8)
    assert len(train) == 2
    assert len(test) == 8
    assert train["t"].max() < test["t"].min()


def test_evaluate_string_labels_reports_all_binary_metrics() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"a": rng.normal(size=60), "b": rng.normal(size=60)})
    df["y"] = np.where(df.a + rng.normal(size=60) * 0.5 > 0, "yes", "no")
    model = ef.ml.fit_estimator(df, estimator="LogisticRegression", target="y")
    metrics = ef.ml.evaluate(model, df).metrics
    for key in ("roc_auc", "average_precision", "brier", "positive_rate"):
        assert key in metrics, key
    assert abs(metrics["positive_rate"] - float((df.y == "yes").mean())) < 1e-12
