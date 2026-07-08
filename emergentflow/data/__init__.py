"""
emergentflow.data
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

from emergentflow.api import public_op
from emergentflow.data.warehouse.introspect import describe_relation
from emergentflow.data.warehouse.query import query

__all__ = ["describe_relation", "load_csv", "load_json", "load_parquet", "load_sample", "query"]


@public_op(name="ef.data.load_csv")
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


@public_op(name="ef.data.load_parquet")
def load_parquet(filepath: str, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Load a Parquet file into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_parquet`` (pyarrow engine). Validates the path at the
    boundary (fail fast, clear errors) and performs no other transformation. ``columns``, when
    given, reads only that subset of columns.
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if not Path(filepath).exists():
        raise FileNotFoundError(f"Parquet file not found: {filepath!r}")
    return pd.read_parquet(filepath, columns=columns)


@public_op(name="ef.data.load_json")
def load_json(filepath: str, *, orient: str | None = None) -> pd.DataFrame:
    """Load a JSON file into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_json``. Validates the path at the boundary and performs no
    other transformation. ``orient`` is passed through to pandas when given (e.g. ``"records"``).
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if not Path(filepath).exists():
        raise FileNotFoundError(f"JSON file not found: {filepath!r}")
    return pd.read_json(filepath, orient=orient)


#: Bundled, permissively-licensed (BSD) sample datasets from scikit-learn, keyed by name.
SAMPLE_DATASETS = ("iris", "wine", "diabetes")


@public_op(name="ef.data.load_sample")
def load_sample(name: str = "iris") -> pd.DataFrame:
    """Load a small bundled sample dataset into a DataFrame (zero filesystem setup).

    Wraps scikit-learn's bundled toy datasets (BSD-licensed): ``"iris"`` and ``"wine"``
    (classification) and ``"diabetes"`` (regression). The returned frame includes the feature
    columns plus a ``target`` column. Lets a brand-new canvas run with nothing on disk.
    """
    if name not in SAMPLE_DATASETS:
        raise ValueError(f"name must be one of {SAMPLE_DATASETS!r}, got {name!r}")
    from sklearn import datasets as _sk

    loader = {"iris": _sk.load_iris, "wine": _sk.load_wine, "diabetes": _sk.load_diabetes}[name]
    return loader(as_frame=True).frame
