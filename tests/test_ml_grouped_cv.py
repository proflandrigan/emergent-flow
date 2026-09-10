"""Regression tests for grouped cross-validation on continuous targets (issue #164 Bug 2).

``ml.cross_validate`` with ``cv_strategy="grouped"`` used to hardwire
``StratifiedGroupKFold``, which sklearn restricts to binary/multiclass targets — so
grouped CV was impossible for every regression estimator. The fix selects the splitter
by target type (``GroupKFold`` for continuous targets) and reports which splitter was
chosen in a ``splitter`` column on the returned frame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from emergentflow.ml import cross_validate


def _make_grouped_df(n_subjects: int = 200, measures: int = 2, seed: int = 0) -> pd.DataFrame:
    """A repeated-measures frame: each subject appears ``measures`` times.

    ``y`` (continuous) is a linear function of ``x`` plus a per-subject random
    intercept, so grouped CV is exactly the right evaluation scheme.
    """
    rng = np.random.default_rng(seed)
    sid = np.tile(np.arange(n_subjects), measures).astype(str)
    u = rng.normal(0, 3, n_subjects)
    x = rng.normal(0, 1, n_subjects * measures)
    subj = np.tile(np.arange(n_subjects), measures)
    y = 2.0 * x + u[subj] + rng.normal(0, 1, n_subjects * measures)
    return pd.DataFrame({"y": y, "x": x, "sid": sid})


def test_grouped_cv_on_continuous_target_uses_groupkfold():
    # Repro from the issue: any regression estimator + cv_strategy="grouped" raised
    # "Supported target types are ('binary', 'multiclass')".
    df = _make_grouped_df()
    res = cross_validate(
        df,
        estimator="Ridge",
        target="y",
        features=["x"],
        cv=4,
        cv_strategy="grouped",
        group_col="sid",
        scoring="r2",
    )
    assert list(res.columns) == ["fold", "test_score", "fit_time", "score_time", "splitter"]
    assert (res["splitter"] == "GroupKFold").all()
    assert len(res) == 4


def test_grouped_cv_on_multiclass_target_uses_stratifiedgroupkfold():
    df = _make_grouped_df()
    rng = np.random.default_rng(1)
    df["cls"] = rng.integers(0, 3, len(df))
    res = cross_validate(
        df,
        estimator="LogisticRegression",
        target="cls",
        features=["x"],
        cv=4,
        cv_strategy="grouped",
        group_col="sid",
        scoring="accuracy",
    )
    assert (res["splitter"] == "StratifiedGroupKFold").all()


def test_grouped_cv_group_col_validation_still_raises():
    df = _make_grouped_df()
    with pytest.raises(ValueError, match="group_col"):
        cross_validate(
            df,
            estimator="Ridge",
            target="y",
            features=["x"],
            cv=2,
            cv_strategy="grouped",
            group_col="nope",
            scoring="r2",
        )


def test_non_grouped_cv_has_no_splitter_column():
    df = _make_grouped_df()
    res = cross_validate(
        df,
        estimator="Ridge",
        target="y",
        features=["x"],
        cv=3,
        scoring="r2",
    )
    assert "splitter" not in res.columns
