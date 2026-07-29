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

import glob
import importlib.util
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.contract import validate_schema
from emergentflow.data.documents import load_documents
from emergentflow.data.errors import (
    DataError,
    DataLoadError,
    MissingOptionalDependencyError,
    SchemaContractError,
)
from emergentflow.data.http.fetch import http_fetch
from emergentflow.data.http.sheets import load_google_sheet
from emergentflow.data.warehouse.introspect import describe_relation
from emergentflow.data.warehouse.query import query

__all__ = [
    "DataError",
    "DataLoadError",
    "describe_relation",
    "http_fetch",
    "load_csv",
    "load_documents",
    "load_excel",
    "load_google_sheet",
    "load_json",
    "load_parquet",
    "load_sample",
    "MissingOptionalDependencyError",
    "query",
    "SchemaContractError",
]


#: Glob metacharacters that mark a *filepath* as a multi-file pattern rather than
#: a literal path. Checked before any filesystem access so a plain path keeps its
#: original single-file code path (and its original FileNotFoundError) exactly.
_GLOB_CHARS = ("*", "?", "[")


def _is_glob(filepath: str) -> bool:
    """Return True if *filepath* contains a glob metacharacter."""
    return any(char in filepath for char in _GLOB_CHARS)


#: URI schemes routed through fsspec rather than the local filesystem. Each maps a
#: user-facing scheme to the object store it addresses; the fsspec filesystem for
#: each ships in the ``[cloud]`` extra, never the base install. ``memory://`` is not
#: a real object store — it is a deliberate test seam so the offline test lane can
#: drive the remote code path with fsspec's built-in in-memory filesystem, without a
#: cloud account or a network.
REMOTE_URI_SCHEMES: tuple[str, ...] = (
    "s3://",
    "gs://",
    "gcs://",
    "az://",
    "abfs://",
    "memory://",
)

#: Pip extra -> probe modules whose absence means the extra is not installed, mirroring
#: ``emergentflow.recommend._EXTRA_PROBE_MODULES``.
_EXTRA_PROBE_MODULES: dict[str, tuple[str, ...]] = {
    "emergentflow[cloud]": ("fsspec",),
    "emergentflow[excel]": ("openpyxl",),
}


def _is_remote_uri(filepath: str) -> bool:
    """Return True if *filepath* addresses a remote object store, not a local path."""
    return filepath.startswith(REMOTE_URI_SCHEMES)


def _require_extra(extra: str) -> None:
    """Raise MissingOptionalDependencyError(extra) unless all of *extra*'s probe modules import."""
    probes = _EXTRA_PROBE_MODULES.get(extra)
    if not probes or any(importlib.util.find_spec(probe) is None for probe in probes):
        raise MissingOptionalDependencyError(extra)


def _resolve_storage_options(connection: str | None) -> dict[str, str]:
    """Resolve object-store credentials for *connection* from the profile store.

    *connection* is a connection-profile **name**, never a credential (ADR 0018).
    The profile's ``credential_refs`` map roles to environment-variable **names**;
    this function reads those env vars and returns the resolved values as fsspec
    ``storage_options``. Returns an empty dict when *connection* is ``None``, so
    anonymous/public reads and locally-configured credential chains (AWS_PROFILE,
    gcloud ADC) keep working untouched.

    This is an EFFECTFUL function (profile-store file I/O + ``os.environ``) — it is
    called only from a loader's edge, never from ``compile_to_code``/``execute``
    internals (ADR 0002 purity).
    """
    if connection is None:
        return {}
    from emergentflow.connections.profiles import UnknownConnectionError, load_profiles

    store = load_profiles()
    try:
        profile = store.get(connection)
    except UnknownConnectionError:
        raise

    credential_refs: dict[str, str] = getattr(profile, "credential_refs", {})
    storage_options: dict[str, str] = {}
    for role, env_name in credential_refs.items():
        value = os.environ.get(env_name)
        if value is None:
            raise DataLoadError(
                f"connection profile {connection!r} references env var {env_name!r} "
                f"for role {role!r}, but it is not set"
            )
        storage_options[role] = value
    return storage_options


def _open_remote(filepath: str, connection: str | None):
    """Open *filepath* on its object store via fsspec, returning a binary file object.

    Raises
    ------
    MissingOptionalDependencyError
        If the ``[cloud]`` extra is not installed, or fsspec itself is present but the
        URI's scheme-specific backend (``s3fs``/``gcsfs``/``adlfs``) is not -- fsspec
        resolves that backend lazily inside ``fsspec.open()`` and raises a bare
        ``ImportError``, which is translated here so a base install (or one with fsspec
        but not the matching backend) never surfaces an opaque ``ImportError``.
    """
    _require_extra("emergentflow[cloud]")
    import fsspec

    try:
        return fsspec.open(filepath, mode="rb", **_resolve_storage_options(connection))
    except ImportError as exc:
        raise MissingOptionalDependencyError("emergentflow[cloud]") from exc


def _read_remote_file(
    filepath: str,
    connection: str | None,
    reader: Callable[[object], pd.DataFrame],
) -> pd.DataFrame:
    """Open one remote object-store file, read it with *reader*, then close the handle.

    The single-file remote path closes its fsspec handle via a ``with`` block; this
    is the equivalent for each match in a remote glob, called once per file from
    inside ``_concat_files``'s reader callback so no handle is left open after the
    read completes.
    """
    with _open_remote(filepath, connection).open() as handle:
        return reader(handle)


def _resolve_remote_glob(filepath: str, connection: str | None, *, kind: str) -> list[str]:
    """Return the sorted list of remote URIs matching the glob *filepath*.

    Mirrors ``_resolve_glob`` for object stores: uses the fsspec filesystem's own
    ``glob``, re-prefixes each match with the original URI scheme (fsspec's glob
    returns bucket-relative paths without it), and sorts for determinism.

    Raises
    ------
    DataLoadError
        If the pattern matches nothing. The message names the pattern and *kind*.
    MissingOptionalDependencyError
        If the ``[cloud]`` extra is not installed, or fsspec itself is present but the
        URI's scheme-specific backend (``s3fs``/``gcsfs``/``adlfs``) is not (see
        ``_open_remote``).
    """
    _require_extra("emergentflow[cloud]")
    import fsspec

    storage_options = _resolve_storage_options(connection)
    try:
        fs, path = fsspec.core.url_to_fs(filepath, **storage_options)
    except ImportError as exc:
        raise MissingOptionalDependencyError("emergentflow[cloud]") from exc
    scheme = filepath[: filepath.index("://") + len("://")]
    matches = sorted(f"{scheme}{m}" for m in fs.glob(path))
    if not matches:
        raise DataLoadError(f"no {kind} files matched {filepath!r}")
    return matches


def _resolve_glob(filepath: str, *, kind: str) -> list[Path]:
    """Return the sorted list of files matching the glob *filepath*.

    Sorted so multi-file concatenation is deterministic — the same pattern always
    produces the same row order, which is what makes golden tests stable.

    Raises
    ------
    DataLoadError
        If the pattern matches nothing. The message names the pattern and *kind*
        (e.g. "CSV"), so an analyst sees "no CSV files matched 'data/*.csv'"
        rather than an empty frame.
    """
    matches = sorted(Path(m) for m in glob.glob(filepath, recursive=True))
    files = [m for m in matches if m.is_file()]
    if not files:
        raise DataLoadError(f"no {kind} files matched {filepath!r}")
    return files


def _concat_files(
    files: list[Path] | list[str],
    reader: Callable[[Path | str], pd.DataFrame],
    *,
    source_file: bool,
) -> pd.DataFrame:
    """Read every path in *files* with *reader* and row-concatenate the results.

    Schemas are aligned by column name (``pandas.concat`` with ``sort=False``);
    a column missing from one file becomes NaN in that file's rows rather than an
    error. The index is reset so the result has a clean RangeIndex instead of
    repeated per-file indices.

    *files* is either local ``Path`` objects or remote URI strings — never mix the
    two by round-tripping a remote URI through ``Path`` (``Path("s3://b/k")``
    silently collapses the double slash), so callers pass whichever type addresses
    their source and *reader* is applied to that same type unchanged.

    When *source_file* is True, each file's rows gain a ``source_file`` column
    holding that file's path as a string, so provenance survives the concat.
    """
    frames = []
    for path in files:
        frame = reader(path)
        if source_file:
            if "source_file" in frame.columns:
                raise DataLoadError(
                    f"cannot add source_file column: {str(path)!r} already has a source_file column"
                )
            frame = frame.assign(source_file=str(path))
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


@public_op(name="ef.data.load_csv")
def load_csv(
    filepath: str,
    *,
    encoding: str = "utf-8",
    source_file: bool = False,
    connection: str | None = None,
    expect_columns: list[str] | None = None,
    expect_dtypes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Load a CSV file — or every CSV matching a glob — into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_csv``. Validates the path at the boundary
    (fail fast, clear errors) and performs no other transformation.

    *filepath* may also be a remote object-storage URI (``s3://``, ``gs://``,
    ``az://``, ...), routed through fsspec (requires the optional ``[cloud]``
    extra). *connection* names a connection profile supplying object-store
    credentials (env-var names only, never a literal secret); ignored for local
    paths.

    When *filepath* contains a glob metacharacter (``*``, ``?``, ``[``), every
    matching file is read and row-concatenated in sorted filename order, so the
    result is deterministic. Set *source_file* to add a ``source_file`` column
    naming the file each row came from.

    *expect_columns* and *expect_dtypes* are an optional schema-on-load contract,
    checked once against the final frame (after any glob concatenation) via
    ``emergentflow.data.contract.validate_schema``.

    Raises
    ------
    ValueError
        If *filepath* is empty or not a string.
    FileNotFoundError
        If *filepath* is a literal path that does not exist.
    DataLoadError
        If *filepath* is a glob that matches no files, or *source_file* is True
        and a loaded file already has a ``source_file`` column.
    MissingOptionalDependencyError
        If *filepath* is a remote URI and the ``[cloud]`` extra is not installed.
    SchemaContractError
        If *expect_columns* or *expect_dtypes* is set and the loaded frame does
        not satisfy it.
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if _is_remote_uri(filepath):
        if _is_glob(filepath):
            uris = _resolve_remote_glob(filepath, connection, kind="CSV")
            frame = _concat_files(
                uris,
                lambda p: _read_remote_file(
                    str(p), connection, lambda h: pd.read_csv(h, encoding=encoding)
                ),
                source_file=source_file,
            )
        else:
            with _open_remote(filepath, connection).open() as handle:
                frame = pd.read_csv(handle, encoding=encoding)
            if source_file:
                frame = _concat_files([filepath], lambda p: frame, source_file=True)
    elif _is_glob(filepath):
        files = _resolve_glob(filepath, kind="CSV")
        frame = _concat_files(
            files, lambda p: pd.read_csv(p, encoding=encoding), source_file=source_file
        )
    else:
        if not Path(filepath).exists():
            raise FileNotFoundError(f"CSV file not found: {filepath!r}")
        frame = pd.read_csv(filepath, encoding=encoding)
        if source_file:
            frame = _concat_files([Path(filepath)], lambda p: frame, source_file=True)
    return validate_schema(frame, expect_columns=expect_columns, expect_dtypes=expect_dtypes)


@public_op(name="ef.data.load_parquet")
def load_parquet(
    filepath: str,
    *,
    columns: list[str] | None = None,
    source_file: bool = False,
    connection: str | None = None,
    expect_columns: list[str] | None = None,
    expect_dtypes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Load a Parquet file — or every Parquet file matching a glob — into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_parquet`` (pyarrow engine). Validates the path at the
    boundary (fail fast, clear errors) and performs no other transformation. ``columns``, when
    given, reads only that subset of columns.

    *filepath* may also be a remote object-storage URI (``s3://``, ``gs://``,
    ``az://``, ...), routed through fsspec (requires the optional ``[cloud]``
    extra). *connection* names a connection profile supplying object-store
    credentials (env-var names only, never a literal secret); ignored for local
    paths.

    When *filepath* contains a glob metacharacter (``*``, ``?``, ``[``), every
    matching file is read and row-concatenated in sorted filename order, so the
    result is deterministic. Set *source_file* to add a ``source_file`` column
    naming the file each row came from.

    *expect_columns* and *expect_dtypes* are an optional schema-on-load contract,
    checked once against the final frame (after any glob concatenation) via
    ``emergentflow.data.contract.validate_schema``.

    Raises
    ------
    ValueError
        If *filepath* is empty or not a string.
    FileNotFoundError
        If *filepath* is a literal path that does not exist.
    DataLoadError
        If *filepath* is a glob that matches no files, or *source_file* is True
        and a loaded file already has a ``source_file`` column.
    MissingOptionalDependencyError
        If *filepath* is a remote URI and the ``[cloud]`` extra is not installed.
    SchemaContractError
        If *expect_columns* or *expect_dtypes* is set and the loaded frame does
        not satisfy it.
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if _is_remote_uri(filepath):
        if _is_glob(filepath):
            uris = _resolve_remote_glob(filepath, connection, kind="Parquet")
            frame = _concat_files(
                uris,
                lambda p: _read_remote_file(
                    str(p), connection, lambda h: pd.read_parquet(h, columns=columns)
                ),
                source_file=source_file,
            )
        else:
            with _open_remote(filepath, connection).open() as handle:
                frame = pd.read_parquet(handle, columns=columns)
            if source_file:
                frame = _concat_files([filepath], lambda p: frame, source_file=True)
    elif _is_glob(filepath):
        files = _resolve_glob(filepath, kind="Parquet")
        frame = _concat_files(
            files, lambda p: pd.read_parquet(p, columns=columns), source_file=source_file
        )
    else:
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Parquet file not found: {filepath!r}")
        frame = pd.read_parquet(filepath, columns=columns)
        if source_file:
            frame = _concat_files([Path(filepath)], lambda p: frame, source_file=True)
    return validate_schema(frame, expect_columns=expect_columns, expect_dtypes=expect_dtypes)


@public_op(name="ef.data.load_json")
def load_json(
    filepath: str,
    *,
    orient: str | None = None,
    lines: bool = False,
    source_file: bool = False,
    connection: str | None = None,
    expect_columns: list[str] | None = None,
    expect_dtypes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Load a JSON file — or every JSON file matching a glob — into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_json``. Validates the path at the boundary and performs no
    other transformation. ``orient`` is passed through to pandas when given (e.g. ``"records"``).
    Set ``lines=True`` to read a ``.jsonl``/newline-delimited-JSON file (one JSON object per line).

    *filepath* may also be a remote object-storage URI (``s3://``, ``gs://``,
    ``az://``, ...), routed through fsspec (requires the optional ``[cloud]``
    extra). *connection* names a connection profile supplying object-store
    credentials (env-var names only, never a literal secret); ignored for local
    paths.

    When *filepath* contains a glob metacharacter (``*``, ``?``, ``[``), every
    matching file is read and row-concatenated in sorted filename order, so the
    result is deterministic. Set *source_file* to add a ``source_file`` column
    naming the file each row came from.

    *expect_columns* and *expect_dtypes* are an optional schema-on-load contract,
    checked once against the final frame (after any glob concatenation) via
    ``emergentflow.data.contract.validate_schema``.

    Raises
    ------
    ValueError
        If *filepath* is empty or not a string.
    FileNotFoundError
        If *filepath* is a literal path that does not exist.
    DataLoadError
        If *filepath* is a glob that matches no files, or *source_file* is True
        and a loaded file already has a ``source_file`` column.
    MissingOptionalDependencyError
        If *filepath* is a remote URI and the ``[cloud]`` extra is not installed.
    SchemaContractError
        If *expect_columns* or *expect_dtypes* is set and the loaded frame does
        not satisfy it.
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if _is_remote_uri(filepath):
        if _is_glob(filepath):
            uris = _resolve_remote_glob(filepath, connection, kind="JSON")
            frame = _concat_files(
                uris,
                lambda p: _read_remote_file(
                    str(p), connection, lambda h: pd.read_json(h, orient=orient, lines=lines)
                ),
                source_file=source_file,
            )
        else:
            with _open_remote(filepath, connection).open() as handle:
                frame = pd.read_json(handle, orient=orient, lines=lines)
            if source_file:
                frame = _concat_files([filepath], lambda p: frame, source_file=True)
    elif _is_glob(filepath):
        files = _resolve_glob(filepath, kind="JSON")
        frame = _concat_files(
            files,
            lambda p: pd.read_json(p, orient=orient, lines=lines),
            source_file=source_file,
        )
    else:
        if not Path(filepath).exists():
            raise FileNotFoundError(f"JSON file not found: {filepath!r}")
        frame = pd.read_json(filepath, orient=orient, lines=lines)
        if source_file:
            frame = _concat_files([Path(filepath)], lambda p: frame, source_file=True)
    return validate_schema(frame, expect_columns=expect_columns, expect_dtypes=expect_dtypes)


@public_op(name="ef.data.load_excel")
def load_excel(
    filepath: str,
    *,
    sheet: str | int = 0,
    header_row: int = 0,
    usecols: str | list[str] | None = None,
    source_file: bool = False,
    connection: str | None = None,
    expect_columns: list[str] | None = None,
    expect_dtypes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Load an Excel workbook — or every workbook matching a glob — into a tidy pandas DataFrame.

    Thin wrapper over ``pandas.read_excel`` (requires the optional ``[excel]`` extra, which
    installs openpyxl). Validates the path at the boundary (fail fast, clear errors) and
    performs no other transformation.

    *sheet* selects a sheet by name or zero-based index (default: the first sheet).
    *header_row* is the zero-based row index to use as the column header. *usecols* is
    passed through to pandas: an Excel range string (e.g. ``"A:D"``) or a list of column
    names.

    *filepath* may also be a remote object-storage URI (``s3://``, ``gs://``,
    ``az://``, ...), routed through fsspec (requires the optional ``[cloud]``
    extra). *connection* names a connection profile supplying object-store
    credentials (env-var names only, never a literal secret); ignored for local
    paths.

    When *filepath* contains a glob metacharacter (``*``, ``?``, ``[``), every
    matching file is read and row-concatenated in sorted filename order, so the
    result is deterministic. Set *source_file* to add a ``source_file`` column
    naming the file each row came from.

    *expect_columns* and *expect_dtypes* are an optional schema-on-load contract,
    checked once against the final frame (after any glob concatenation) via
    ``emergentflow.data.contract.validate_schema``.

    Raises
    ------
    ValueError
        If *filepath* is empty or not a string, or *sheet* is ``None`` (pandas would
        return a dict of frames, one per sheet, instead of a single DataFrame — select
        one sheet by name or index).
    FileNotFoundError
        If *filepath* is a literal path that does not exist.
    DataLoadError
        If *filepath* is a glob that matches no files, *source_file* is True and a
        loaded file already has a ``source_file`` column, or *sheet* names a sheet
        that does not exist in the workbook.
    MissingOptionalDependencyError
        If the ``[excel]`` extra is not installed, or *filepath* is a remote URI and
        the ``[cloud]`` extra is not installed.
    SchemaContractError
        If *expect_columns* or *expect_dtypes* is set and the loaded frame does
        not satisfy it.
    """
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    _require_extra("emergentflow[excel]")
    if sheet is None:
        raise ValueError(
            "sheet must not be None: reading every sheet at once is not supported "
            "(pandas.read_excel(sheet_name=None) returns a dict of frames, not a "
            "single DataFrame); select one sheet by name or index"
        )

    def _read_excel(source: object, *, display: object) -> pd.DataFrame:
        try:
            return pd.read_excel(source, sheet_name=sheet, header=header_row, usecols=usecols)
        except ValueError as exc:
            raise DataLoadError(f"sheet {sheet!r} not found in Excel file {display!r}") from exc

    if _is_remote_uri(filepath):
        if _is_glob(filepath):
            uris = _resolve_remote_glob(filepath, connection, kind="Excel")
            frame = _concat_files(
                uris,
                lambda p: _read_remote_file(
                    str(p), connection, lambda h: _read_excel(h, display=p)
                ),
                source_file=source_file,
            )
        else:
            with _open_remote(filepath, connection).open() as handle:
                frame = _read_excel(handle, display=filepath)
            if source_file:
                frame = _concat_files([filepath], lambda p: frame, source_file=True)
    elif _is_glob(filepath):
        files = _resolve_glob(filepath, kind="Excel")
        frame = _concat_files(files, lambda p: _read_excel(p, display=p), source_file=source_file)
    else:
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Excel file not found: {filepath!r}")
        frame = _read_excel(filepath, display=filepath)
        if source_file:
            frame = _concat_files([Path(filepath)], lambda p: frame, source_file=True)
    return validate_schema(frame, expect_columns=expect_columns, expect_dtypes=expect_dtypes)


# The "web_traffic", "reviews", and "transactions" sample datasets below are generated
# deterministically in code from a fixed seed rather than vendored as data files, because:
#   - there is no licensing question at all -- generated data has no upstream license,
#     unlike the first three datasets, which wrap scikit-learn's BSD-licensed toy datasets;
#   - it avoids checking any binary/large data files into the repo;
#   - it is deterministic -- a fixed seed means the same frame every call, so goldens and
#     the ADR-0002 compile_to_code(ir) == execute(ir) equivalence gate stay stable.

#: Bundled sample datasets, keyed by name. The first three wrap scikit-learn's toy
#: datasets (BSD-licensed); the last three are generated deterministically in-process
#: from a fixed seed, so they carry no upstream license and add no data files to the
#: repo (see the builders below).
SAMPLE_DATASETS = (
    "iris",
    "wine",
    "diabetes",
    "web_traffic",
    "reviews",
    "transactions",
)

#: Seed fixed so every generated sample dataset is byte-identical across calls and
#: processes -- goldens and the ADR-0002 equivalence gate depend on it.
_SAMPLE_SEED = 20260728


def _build_web_traffic() -> pd.DataFrame:
    """Daily web-traffic time series: 365 rows with trend, weekly seasonality, and noise."""
    rng = np.random.default_rng(_SAMPLE_SEED)
    dates = pd.date_range(start="2025-01-01", periods=365, freq="D")
    day_index = np.arange(365)
    trend = 500 + day_index * 1.5
    weekly = 150 * np.sin(2 * np.pi * day_index / 7)
    noise = rng.normal(loc=0, scale=40, size=365)
    sessions = np.clip(trend + weekly + noise, 10, None).astype(int)
    conversion_noise = rng.normal(loc=0, scale=3, size=365)
    conversions = np.clip(sessions * 0.04 + conversion_noise, 0, None).astype(int)
    channels = ["organic", "paid", "referral"]
    channel = [channels[i % len(channels)] for i in day_index]
    return pd.DataFrame(
        {
            "date": dates,
            "sessions": sessions,
            "conversions": conversions,
            "channel": channel,
        }
    )


def _build_reviews() -> pd.DataFrame:
    """Short product-review text corpus: 200 rows of text plus rating and category."""
    rng = np.random.default_rng(_SAMPLE_SEED)
    openers = ["Honestly,", "Overall,", "So far,", "After a week,", "To be fair,"]
    subjects = ["this product", "the item", "this purchase", "the gadget", "this order"]
    sentiments = [
        ("exceeded my expectations and I would buy it again", 5),
        ("works great and was worth every penny", 4),
        ("is fine, does what it says", 3),
        ("was disappointing and broke quickly", 2),
        ("is a total waste of money", 1),
    ]
    categories = ["electronics", "home", "beauty", "sports", "toys"]
    n = 200
    opener_idx = rng.integers(0, len(openers), size=n)
    subject_idx = rng.integers(0, len(subjects), size=n)
    sentiment_idx = rng.integers(0, len(sentiments), size=n)
    category_idx = rng.integers(0, len(categories), size=n)
    verified = rng.random(n) < 0.7
    texts = []
    ratings = []
    for i in range(n):
        clause, rating = sentiments[sentiment_idx[i]]
        texts.append(f"{openers[opener_idx[i]]} {subjects[subject_idx[i]]} {clause}.")
        ratings.append(rating)
    return pd.DataFrame(
        {
            "review_id": np.arange(1, n + 1),
            "text": texts,
            "rating": ratings,
            "category": [categories[i] for i in category_idx],
            "verified": verified,
        }
    )


def _build_transactions() -> pd.DataFrame:
    """Retail transaction/event table: 500 rows suitable for cohort and funnel analysis."""
    rng = np.random.default_rng(_SAMPLE_SEED)
    n = 500
    n_customers = 80
    customer_id = rng.integers(1, n_customers + 1, size=n)
    start = pd.Timestamp("2025-01-01")
    seconds_in_year = 365 * 24 * 60 * 60
    offsets = rng.integers(0, seconds_in_year, size=n)
    timestamp = start + pd.to_timedelta(offsets, unit="s")
    amount = np.round(rng.gamma(shape=2.0, scale=25.0, size=n) + 1, 2)
    categories = ["electronics", "home", "beauty", "sports", "toys"]
    category_idx = rng.integers(0, len(categories), size=n)
    events = ["view", "add_to_cart", "purchase"]
    event_weights = [0.5, 0.3, 0.2]
    event_idx = rng.choice(len(events), size=n, p=event_weights)
    frame = pd.DataFrame(
        {
            "transaction_id": np.arange(1, n + 1),
            "customer_id": customer_id,
            "timestamp": timestamp,
            "amount": amount,
            "product_category": [categories[i] for i in category_idx],
            "event": [events[i] for i in event_idx],
        }
    )
    return frame.sort_values("timestamp").reset_index(drop=True)


@public_op(name="ef.data.load_sample")
def load_sample(name: str = "iris") -> pd.DataFrame:
    """Load a small bundled sample dataset into a DataFrame (zero filesystem setup).

    Six datasets are bundled, split across two families:

    - ``"iris"``, ``"wine"`` (classification), and ``"diabetes"`` (regression) wrap
      scikit-learn's bundled toy datasets (BSD-3-Clause licensed, real-world data).
      The returned frame includes the feature columns plus a ``target`` column.
    - ``"web_traffic"``, ``"reviews"``, and ``"transactions"`` are synthetic data,
      generated deterministically in-process from a fixed seed (no upstream license,
      not real-world data): ``"web_traffic"`` is a daily time series feeding the
      ``timeseries`` node family, ``"reviews"`` is a short text corpus feeding the
      text/LLM node family, and ``"transactions"`` is a retail transaction/event table
      feeding cohort and funnel product-analytics analysis.

    Lets a brand-new canvas run with nothing on disk.
    """
    if name not in SAMPLE_DATASETS:
        raise ValueError(f"name must be one of {SAMPLE_DATASETS!r}, got {name!r}")
    generated = {
        "web_traffic": _build_web_traffic,
        "reviews": _build_reviews,
        "transactions": _build_transactions,
    }
    if name in generated:
        return generated[name]()
    from sklearn import datasets as _sk

    loader = {"iris": _sk.load_iris, "wine": _sk.load_wine, "diabetes": _sk.load_diabetes}[name]
    return loader(as_frame=True).frame
