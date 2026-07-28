"""
emergentflow.data.contract
~~~~~~~~~~~~~~~~~~~~~~~~~~
The single schema-on-load gate every loader routes through, so every loader
accepts and rejects identical contracts; the Story 19 ``assert_data`` quality
gate reuses it rather than reimplementing column checks.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.data.errors import SchemaContractError

__all__ = ["validate_schema"]


def validate_schema(
    frame: pd.DataFrame,
    *,
    expect_columns: list[str] | None = None,
    expect_dtypes: dict[str, str] | None = None,
    allow_extra_columns: bool = True,
) -> pd.DataFrame:
    """Validate *frame*'s schema against an optional column/dtype contract.

    Parameters
    ----------
    frame:
        The DataFrame to validate. Never mutated or copied — returned as-is.
    expect_columns:
        Optional list of column names that must be present in *frame*. Missing
        columns are collected and reported together, not raised on the first miss.
    expect_dtypes:
        Optional map of column name to expected pandas dtype **string** (e.g.
        ``"int64"``, ``"float64"``, ``"object"``, ``"bool"``,
        ``"datetime64[ns]"``). A column named here but absent from *frame* is
        reported as a missing column (same path as ``expect_columns``); a
        present column whose dtype string does not match is reported as a
        mistyped column.

        Dtypes are compared as strings via ``str(series.dtype)`` rather than
        constructed numpy dtype objects — deliberate: it keeps the contract
        JSON-native (it has to survive a trip through the IR) and avoids a
        numpy-version-dependent equality surprise.
    allow_extra_columns:
        When False, any column present in *frame* but not named in
        *expect_columns* is reported as an extra column. Default True.

    Returns
    -------
    pd.DataFrame
        *frame*, unchanged, when validation passes (both ``expect_columns`` and
        ``expect_dtypes`` ``None`` is a fast path — no work is done).

    Raises
    ------
    SchemaContractError
        If any column is missing, any column is unexpectedly extra (only when
        ``allow_extra_columns=False``), or any column's dtype does not match.
        All problems found are collected and reported together in a single
        error, with the three categories clearly separated.
    """
    if expect_columns is None and expect_dtypes is None:
        return frame

    present_columns = set(frame.columns)
    expected_columns = set(expect_columns or [])
    dtype_columns = set(expect_dtypes or {})

    missing: set[str] = (expected_columns | dtype_columns) - present_columns
    extra: set[str] = set()
    if not allow_extra_columns and expect_columns is not None:
        extra = present_columns - expected_columns

    mistyped: list[str] = []
    if expect_dtypes:
        for column, expected_dtype in sorted(expect_dtypes.items()):
            if column in missing:
                continue
            actual_dtype = str(frame[column].dtype)
            if actual_dtype != expected_dtype:
                mistyped.append(f"{column}: expected {expected_dtype}, got {actual_dtype}")

    if not missing and not extra and not mistyped:
        return frame

    lines = []
    if missing:
        lines.append(f"missing columns: {sorted(missing)}")
        lines.append(f"present columns: {sorted(present_columns)}")
    if extra:
        lines.append(f"unexpected extra columns: {sorted(extra)}")
    if mistyped:
        lines.append(f"mistyped columns: {mistyped}")
    raise SchemaContractError("schema contract violated: " + "; ".join(lines))
