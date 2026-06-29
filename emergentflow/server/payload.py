"""Result-payload contract for the local server (ADR 0013, §A6).

``ef.execute`` returns *inspectable* objects (ADR 0002) keyed by OUT-port name,
but inspectable is a **superset** of JSON-native: a ``pandas.DataFrame`` or a
``@dataclass``/Pydantic result is inspectable yet not directly serializable.
``to_payload`` is a single pure function that coerces any such artifact into a
JSON-safe **tagged union** -- a dict with a ``"kind"`` discriminator -- that the
frontend (roadmap Epic 8) can render without knowing Python types. It has no I/O
and touches no global state; pandas/pydantic/matplotlib are imported lazily inside
the function so importing this module stays light and ``torch`` is never imported
(unsupported objects, including ``torch.nn.Module``, are detected structurally).
Supported kinds include ``"image"`` (matplotlib figures serialised as base64 PNG
with a 2 MB cap) and ``"html"`` (HTML-document strings embedded verbatim, no
truncation).
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

PAYLOAD_CONTRACT_VERSION = 2  # standalone; NOT tied to IR schema_version
MAX_HEAD_ROWS = 50  # DataFrame rows sampled into `head`
MAX_TEXT_CHARS = 16384  # cap for long strings / repr fallback
MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB cap for base64 image payloads


def _sanitize_nonfinite(value: Any) -> Any:
    """Recursively replace NaN/Infinity floats with ``None``.

    ``json.dumps`` defaults to ``allow_nan=True``, which silently writes the
    non-standard ``NaN``/``Infinity``/``-Infinity`` tokens -- valid to Python's own
    decoder but **not** valid JSON, so a browser's ``JSON.parse`` (the actual
    consumer of this contract) would choke on them. Pre-walk the structure and
    remap non-finite floats to ``None``, matching how ``DataFrame.to_json``
    already maps NaN to ``null``, before handing off to ``json.dumps``.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _sanitize_nonfinite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_nonfinite(v) for v in value]
    return value


def to_payload(value: Any) -> dict[str, Any]:
    """Coerce an ``execute()`` artifact into a JSON-safe tagged-union payload.

    Dispatch order matters and checks the most specific shape first: scalar/text
    strings, then ``pandas.DataFrame``, then dataclass/Pydantic records (which
    recurse into ``to_payload`` for their fields so a nested DataFrame still
    becomes a ``"table"``), then generic JSON containers, falling back to
    ``"unsupported"`` for anything else (e.g. a ``torch.nn.Module``).
    """
    if value is None or isinstance(value, (bool, int, float)):
        return {"kind": "scalar", "value": _sanitize_nonfinite(value)}

    if isinstance(value, str):
        lowered = value.lstrip()[:16].lower()
        if lowered.startswith("<!doctype html") or lowered.startswith("<html"):
            return {"kind": "html", "value": value, "truncated": False}
        if len(value) <= MAX_TEXT_CHARS:
            return {"kind": "scalar", "value": value}
        return {
            "kind": "text",
            "value": value[:MAX_TEXT_CHARS],
            "length": len(value),
            "truncated": True,
        }

    import numpy as np

    # numpy scalars (np.int64, np.bool_, np.float32, ...) are NOT Python
    # int/bool subclasses, so without this they'd fall through to "unsupported".
    # (np.float64/np.str_ ARE native subclasses and were handled above.) Convert
    # to the native Python scalar via .item() and re-dispatch so it lands in the
    # "scalar" branch with the same NaN/Inf sanitizing.
    if isinstance(value, np.generic):
        return to_payload(value.item())

    try:
        import matplotlib.figure as _mpl_figure

        if isinstance(value, _mpl_figure.Figure):
            import base64
            import io

            buf = io.BytesIO()
            value.savefig(buf, format="png", bbox_inches="tight")
            raw = buf.getvalue()
            if len(raw) > MAX_IMAGE_BYTES:
                return {
                    "kind": "unsupported",
                    "type": type(value).__name__,
                    "repr": f"<Figure: PNG {len(raw)} bytes exceeds {MAX_IMAGE_BYTES} byte limit>",
                }
            width, height = value.canvas.get_width_height()
            return {
                "kind": "image",
                "mime": "image/png",
                "data": base64.b64encode(raw).decode("ascii"),
                "width": int(width),
                "height": int(height),
            }
    except ImportError:
        pass

    import pandas as pd

    if isinstance(value, pd.DataFrame):
        sample = value.head(MAX_HEAD_ROWS)
        try:
            # to_json(orient="records") requires unique column labels; most
            # DataFrames satisfy that, but a duplicate-column frame (e.g. from a
            # merge/pivot upstream) would otherwise raise and crash the whole
            # /execute response instead of degrading this one OUT port.
            head = json.loads(sample.to_json(orient="records"))
        except ValueError:
            head = [
                {str(col): cell for col, cell in zip(value.columns, row, strict=True)}
                for row in sample.itertuples(index=False, name=None)
            ]
            head = json.loads(json.dumps(_sanitize_nonfinite(head), default=str))
        return {
            "kind": "table",
            "columns": [str(c) for c in value.columns],
            "dtypes": [str(dt) for dt in value.dtypes],
            "shape": [int(value.shape[0]), int(value.shape[1])],
            "head": head,
            "truncated": bool(value.shape[0] > MAX_HEAD_ROWS),
        }

    if isinstance(value, pd.Series):
        df = value.to_frame()
        return to_payload(df)

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: to_payload(getattr(value, f.name)) for f in dataclasses.fields(value)}
        return {"kind": "record", "type": type(value).__name__, "fields": fields}

    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        fields = {name: to_payload(getattr(value, name)) for name in value.__class__.model_fields}
        return {"kind": "record", "type": type(value).__name__, "fields": fields}

    if isinstance(value, (list, tuple, dict)):
        try:
            return {"kind": "json", "value": json.loads(json.dumps(_sanitize_nonfinite(value)))}
        except (TypeError, ValueError):
            pass

    return {
        "kind": "unsupported",
        "type": type(value).__name__,
        "repr": repr(value)[:MAX_TEXT_CHARS],
    }
