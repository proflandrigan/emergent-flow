"""Full-frame browsing for the inspector (issue #178): ``POST /browse/frame``.

``to_payload`` only ships a 50-row ``head`` preview, which is useless for finding one row in a
large table. This service reads the *full* stored DataFrame back out of the artifact store and
serves a filtered / sorted / projected window of it. Order of operations is fixed: filter ->
sort -> project -> slice. ``total_rows`` counts the stored frame before filters and
``filtered_rows`` after. Every returned row carries ``_row``, its original positional index in
the stored frame, so a row stays identifiable under any filter or sort (and sort ties break on
it, making pagination stable). Read-only: nothing here mutates the graph or the store.

Column names on the wire are ``str(label)`` -- the same stringification the 50-row preview uses,
so integer labels (``0``, ``2020``) and MultiIndex tuples (``"('x', 'a')"``) round-trip. Columns
are resolved to *positions* internally, so non-string and duplicate labels never reach a label
lookup. A name shared by several columns is ambiguous: showing it is fine (all copies are
listed), but filtering, sorting or projecting by it is a 422 rather than a guess.

Failures that are not a "this output is gone" condition (unknown column, bad operator, bad
value) raise, which ``_safe_json`` maps to the project's 422 ``{"error": ...}`` contract.
"""

from __future__ import annotations

from typing import Any

from emergentflow.clean import OPERATORS, filter_rows
from emergentflow.server.artifacts import get_default_artifacts
from emergentflow.server.payload import frame_window_to_records

DEFAULT_LIMIT = 100
MAX_LIMIT = 500  # rows per page, hard cap
MAX_CELL_CHARS = 200  # long cells (e.g. embedding vectors) are cut with an ellipsis
# Internal working-frame labels: data columns become ``c0, c1, ...`` and the original row
# position lives in ``_row`` -- disjoint by construction, so no user column can collide.
_ROW_COL = "_row"


def _coerce(series: Any, value: Any, name: str) -> Any:
    """Coerce a JSON filter *value* to the column's dtype (numeric / bool / datetime)."""
    import pandas as pd

    if isinstance(value, (list, tuple)):
        return [_coerce(series, v, name) for v in value]
    if value is None:
        return None
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "false"):
                return lowered == "true"
            raise ValueError(f"cannot interpret {value!r} as a boolean for column {name!r}")
        return bool(value)
    if pd.api.types.is_numeric_dtype(dtype):
        is_int_col = pd.api.types.is_integer_dtype(dtype)
        if is_int_col and isinstance(value, int) and not isinstance(value, bool):
            return value  # exact: never round-trip a large int through float
        if is_int_col and isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                pass  # e.g. "2.5" -- fall through to float
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"cannot interpret {value!r} as a number for column {name!r}"
            ) from None
        return int(number) if is_int_col and number.is_integer() else number
    if pd.api.types.is_datetime64_any_dtype(dtype):
        stamp = pd.Timestamp(value)
        column_tz = getattr(dtype, "tz", None)
        if column_tz is not None:
            # naive value -> read in the column's zone; aware value -> convert to it
            stamp = (
                stamp.tz_localize(column_tz)
                if stamp.tzinfo is None
                else stamp.tz_convert(column_tz)
            )
        elif stamp.tzinfo is not None:
            # naive column: compare as naive UTC, the convention pandas uses for naive stamps
            stamp = stamp.tz_convert("UTC").tz_localize(None)
        return stamp
    return value


def _int_arg(payload: dict[str, Any], key: str, default: int) -> int:
    raw = payload.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{key!r} must be an integer; got {raw!r}")
    return raw


def _resolve(names: list[str], name: Any, what: str) -> int:
    """Map a client-sent (stringified) column *name* to its position in the stored frame."""
    if not isinstance(name, str) or name not in names:
        raise ValueError(f"unknown {what} {name!r}; expected one of {names!r}")
    positions = [i for i, n in enumerate(names) if n == name]
    if len(positions) > 1:
        raise ValueError(
            f"ambiguous {what} {name!r}: {len(positions)} columns share that name "
            f"(positions {positions}); rename them upstream to filter, sort or select by it"
        )
    return positions[0]


def browse_frame(payload: dict[str, Any]) -> dict[str, Any]:
    """``POST /browse/frame``: window over a node's stored DataFrame output.

    Request: ``{node_id, port?, revision?, columns?, filters?: [{column, operator, value}],
    sort?: [{column, ascending}], offset=0, limit=100}`` (``limit`` is clamped to 500).
    Response ``status`` is ``ok`` (with ``revision, columns, dtypes, total_rows, filtered_rows,
    offset, limit, rows``), ``expired`` (nothing stored), ``revision_mismatch`` (stored output
    was replaced; carries ``current_revision``) or ``not_tabular``.
    """
    import numpy as np
    import pandas as pd

    node_id = payload.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("browse_frame requires a non-empty 'node_id'")
    offset = _int_arg(payload, "offset", 0)
    limit = _int_arg(payload, "limit", DEFAULT_LIMIT)
    if offset < 0:
        raise ValueError(f"'offset' must be >= 0; got {offset}")
    if limit < 1:
        raise ValueError(f"'limit' must be >= 1; got {limit}")
    limit = min(limit, MAX_LIMIT)
    filters = payload.get("filters") or []
    sorts = payload.get("sort") or []
    columns = payload.get("columns")
    if not isinstance(filters, list) or not isinstance(sorts, list):
        raise ValueError("'filters' and 'sort' must be lists")
    if columns is not None and not (
        isinstance(columns, list) and all(isinstance(c, str) for c in columns)
    ):
        raise ValueError("'columns' must be a list of column names")

    hit = get_default_artifacts().get_with_revision(node_id)
    if hit is None:
        return {"status": "expired"}
    outputs, current_revision = hit
    requested = payload.get("revision")
    if requested is not None and requested != current_revision:
        return {"status": "revision_mismatch", "current_revision": current_revision}

    port = payload.get("port")
    if port is not None and not isinstance(port, str):
        raise ValueError(f"'port' must be a string port name; got {port!r}")
    if port is None:
        port = (
            "frame"
            if "frame" in outputs
            else next((name for name, v in outputs.items() if isinstance(v, pd.DataFrame)), None)
        )
    elif port not in outputs:
        raise ValueError(f"unknown port {port!r}; expected one of {list(outputs)!r}")
    frame = outputs.get(port) if port is not None else None
    if not isinstance(frame, pd.DataFrame):
        return {"status": "not_tabular", "revision": current_revision}

    total_rows = int(frame.shape[0])
    names = [str(c) for c in frame.columns]  # wire names, as in the preview
    # Work on positional labels so int / tuple / duplicate labels never hit a label lookup,
    # and carry the original row position as ``_row`` so it survives filter/sort.
    work = frame.copy(deep=False)
    work.columns = [f"c{i}" for i in range(len(names))]
    work[_ROW_COL] = np.arange(total_rows)
    for spec in filters:
        if not isinstance(spec, dict):
            raise ValueError("each filter must be an object {column, operator, value}")
        column = spec.get("column")
        operator = spec.get("operator", "==")
        if operator not in OPERATORS:
            raise ValueError(f"unknown operator {operator!r}; expected one of {list(OPERATORS)!r}")
        pos = _resolve(names, column, "column")
        value = _coerce(frame.iloc[:, pos], spec.get("value"), names[pos])
        work = filter_rows(work, column=f"c{pos}", operator=operator, value=value)
    filtered_rows = int(work.shape[0])

    if sorts:
        keys: list[str] = []
        ascending: list[bool] = []
        for spec in sorts:
            column = spec.get("column") if isinstance(spec, dict) else None
            pos = _resolve(names, column, "sort column")
            direction = spec.get("ascending", True)
            if not isinstance(direction, bool):
                raise ValueError(f"sort 'ascending' must be true or false; got {direction!r}")
            keys.append(f"c{pos}")
            ascending.append(direction)
        # Tiebreak on the original position so equal keys keep a deterministic order.
        work = work.sort_values(
            by=[*keys, _ROW_COL], ascending=[*ascending, True], kind="mergesort", na_position="last"
        )

    if columns is not None:
        shown = [_resolve(names, c, "column") for c in columns]
    else:
        shown = list(range(len(names)))
    window = work.iloc[offset : offset + limit]
    projected = window.iloc[:, shown]
    projected.columns = [names[i] for i in shown]
    rows = frame_window_to_records(projected, max_cell_chars=MAX_CELL_CHARS)
    for record, position in zip(rows, window[_ROW_COL].tolist(), strict=True):
        record["_row"] = int(position)
    return {
        "status": "ok",
        "revision": current_revision,
        "columns": [names[i] for i in shown],
        "dtypes": [str(frame.dtypes.iloc[i]) for i in shown],
        "total_rows": total_rows,
        "filtered_rows": filtered_rows,
        "offset": offset,
        "limit": limit,
        "rows": rows,
    }
