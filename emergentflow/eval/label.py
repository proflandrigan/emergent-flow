"""
emergentflow.eval.label
~~~~~~~~~~~~~~~~~~~~~~~
Pure label-merge function (Epic 9 Story 6, `ef.eval.label`).

Human labels are captured as input data -- a separate `labels_df` built by a
later Prompt Lab UI story from click/annotation events -- rather than as
interactive I/O inside `execute`. `label()` is the pure join that merges that
`labels_df` onto `ef.eval.run`'s (Epic 9 Story 5) tidy results DataFrame, on
`(row_id, variant)`, where `variant` is derived from `results_df`'s
`provider`/`model` columns rather than being a literal column on either
input. Unlabeled result rows survive the join with `None`/`NaN` label
columns, so partially-labeled runs round-trip cleanly.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op

_REQUIRED_LABEL_COLUMNS = ("row_id", "variant", "label")
_OPTIONAL_LABEL_COLUMNS = ("score", "rubric", "note")


class LabelColumnError(ValueError):
    """Raised by `label()` when `labels_df` is missing a required column or has
    a duplicate (row_id, variant) pair.
    """


@public_op(name="ef.eval.label")
def label(results_df: pd.DataFrame, labels_df: pd.DataFrame) -> pd.DataFrame:
    """Left-merge human labels onto an `ef.eval.run` results DataFrame.

    Parameters
    ----------
    results_df:
        The tidy DataFrame produced by `ef.eval.run`, one row per
        `(row_id, variant)`. `variant` is derived here as
        `provider + ":" + model`, not read from a literal column.
    labels_df:
        Label rows keyed by `row_id` (int-like) and `variant` (str, same
        `"provider:model"` shape), with a required `label` column and
        optional `score` (float), `rubric` (str), `note` (str) columns.

    Returns
    -------
    pd.DataFrame
        Every column of *results_df* (unchanged, original order), then
        `variant`, then `label`, `score`, `rubric`, `note`. Every row of
        *results_df* appears exactly once; rows with no matching label get
        `NaN`/`None` for `label`/`score`/`rubric`/`note`.

    Raises
    ------
    LabelColumnError
        If *labels_df* is missing `row_id`, `variant`, or `label`, or has
        more than one row for the same `(row_id, variant)` pair.
    """
    missing = [c for c in _REQUIRED_LABEL_COLUMNS if c not in labels_df.columns]
    if missing:
        raise LabelColumnError(f"label: labels_df missing required column(s): {missing}")

    if labels_df.duplicated(subset=["row_id", "variant"]).any():
        raise LabelColumnError(
            "label: labels_df has duplicate (row_id, variant) pairs; "
            "each cell may have at most one label"
        )

    results_df = results_df.copy()
    results_df["variant"] = results_df["provider"] + ":" + results_df["model"]

    labels_df = labels_df.copy()
    for optional_col in _OPTIONAL_LABEL_COLUMNS:
        if optional_col not in labels_df.columns:
            labels_df[optional_col] = None

    return results_df.merge(labels_df, how="left", on=["row_id", "variant"])
