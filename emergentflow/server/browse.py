"""Full-frame browsing for the inspector (issue #178): ``POST /browse/frame``.

``to_payload`` only ships a 50-row ``head`` preview, which is useless for finding one row in a
large table. This service reads the *full* stored DataFrame back out of the artifact store and
serves a filtered / sorted / projected window of it. Order of operations is fixed: filter ->
sort -> project -> slice. ``total_rows`` counts the stored frame before filters and
``filtered_rows`` after. Every returned row carries ``_row``, its original positional index in
the stored frame, so a row stays identifiable under any filter or sort (and sort ties break on
it, making pagination stable). Read-only: nothing here mutates the graph or the store.

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
_ROW_COL = "__ef_row__"  # internal; surfaced to clients as ``_row``


def _coerce(series: Any, value: Any) -> Any:
    """Coerce a JSON filter *value* to the column's dtype (numeric / bool / datetime)."""
    import pandas as pd

    if isinstance(value, (list, tuple)):
        return [_coerce(series, v) for v in value]
    if value is None:
        return None
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "false"):
                return lowered == "true"
            raise ValueError(f"cannot interpret {value!r} as a boolean for column {series.name!r}")
        return bool(value)
    if pd.api.types.is_numeric_dtype(dtype):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"cannot interpret {value!r} as a number for column {series.name!r}"
            ) from None
        return (
            int(number) if pd.api.types.is_integer_dtype(dtype) and number.is_integer() else number
        )
    if pd.api.types.is_datetime64_any_dtype(dtype):
        stamp = pd.Timestamp(value)
        if getattr(dtype, "tz", None) is not None and stamp.tzinfo is None:
            stamp = stamp.tz_localize(dtype.tz)
        return stamp
    return value


def _int_arg(payload: dict[str, Any], key: str, default: int) -> int:
    raw = payload.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{key!r} must be an integer; got {raw!r}")
    return raw


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
    # Carry the original positional index as a real column so it survives filter/sort.
    work = frame.copy(deep=False)
    work[_ROW_COL] = np.arange(total_rows)
    for spec in filters:
        if not isinstance(spec, dict):
            raise ValueError("each filter must be an object {column, operator, value}")
        column = spec.get("column")
        operator = spec.get("operator", "==")
        if operator not in OPERATORS:
            raise ValueError(f"unknown operator {operator!r}; expected one of {list(OPERATORS)!r}")
        if not isinstance(column, str) or column not in frame.columns:
            raise ValueError(f"unknown column {column!r}; expected one of {list(frame.columns)!r}")
        value = _coerce(frame[column], spec.get("value"))
        work = filter_rows(work, column=column, operator=operator, value=value)
    filtered_rows = int(work.shape[0])

    if sorts:
        keys: list[str] = []
        ascending: list[bool] = []
        for spec in sorts:
            column = spec.get("column") if isinstance(spec, dict) else None
            if not isinstance(column, str) or column not in frame.columns:
                raise ValueError(
                    f"unknown sort column {column!r}; expected one of {list(frame.columns)!r}"
                )
            keys.append(column)
            ascending.append(bool(spec.get("ascending", True)))
        # Tiebreak on the original position so equal keys keep a deterministic order.
        work = work.sort_values(
            by=[*keys, _ROW_COL], ascending=[*ascending, True], kind="mergesort", na_position="last"
        )

    if columns is not None:
        unknown = [c for c in columns if c not in frame.columns]
        if unknown:
            raise ValueError(
                f"unknown columns {unknown!r}; expected one of {list(frame.columns)!r}"
            )
        shown = list(columns)
    else:
        shown = [str(c) for c in frame.columns]
    window = work.iloc[offset : offset + limit]
    rows = frame_window_to_records(window[shown], max_cell_chars=MAX_CELL_CHARS)
    for record, position in zip(rows, window[_ROW_COL].tolist(), strict=True):
        record["_row"] = int(position)
    return {
        "status": "ok",
        "revision": current_revision,
        "columns": shown,
        "dtypes": [str(frame[c].dtype) for c in shown],
        "total_rows": total_rows,
        "filtered_rows": filtered_rows,
        "offset": offset,
        "limit": limit,
        "rows": rows,
    }
