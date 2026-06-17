"""
colonymind.data
~~~~~~~~~~~~~~~~
Data-ingestion operations (Epic 1, Story 8).

Thin wrappers over pandas for loading external data into tidy DataFrames.
Each public operation validates its inputs at the boundary (fail fast, clear
typed errors) and otherwise defers entirely to the underlying, trusted
library — no reimplementation, no hidden transformation.

See ``docs/public-api-conventions.md`` and ``docs/sdk-design-philosophy.md``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from colonymind.api import public_op

__all__ = ["load_csv"]


@public_op(name="cm.data.load_csv")
def load_csv(filepath: str, *, encoding: str = "utf-8") -> pd.DataFrame:
    """Load a CSV file into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_csv``. Validates the path at the boundary
    (fail fast, clear errors) and performs no other transformation.
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if not Path(filepath).exists():
        raise FileNotFoundError(f"CSV file not found: {filepath!r}")
    return pd.read_csv(filepath, encoding=encoding)
