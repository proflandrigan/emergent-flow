"""Result-payload contract for the local server (ADR 0013, §A6).

``cm.execute`` returns *inspectable* objects (ADR 0002) keyed by OUT-port name,
but inspectable is a **superset** of JSON-native: a ``pandas.DataFrame`` or a
``@dataclass``/Pydantic result is inspectable yet not directly serializable.
``to_payload`` is a single pure function that coerces any such artifact into a
JSON-safe **tagged union** -- a dict with a ``"kind"`` discriminator -- that the
frontend (roadmap Epic 8) can render without knowing Python types. It has no I/O
and touches no global state; pandas/pydantic are imported lazily inside the
function so importing this module stays light and ``torch`` is never imported
(unsupported objects, including ``torch.nn.Module``, are detected structurally).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

PAYLOAD_CONTRACT_VERSION = 1  # standalone; NOT tied to IR schema_version
MAX_HEAD_ROWS = 50  # DataFrame rows sampled into `head`
MAX_TEXT_CHARS = 16384  # cap for long strings / repr fallback


def to_payload(value: Any) -> dict[str, Any]:
    """Coerce an ``execute()`` artifact into a JSON-safe tagged-union payload.

    Dispatch order matters and checks the most specific shape first: scalar/text
    strings, then ``pandas.DataFrame``, then dataclass/Pydantic records (which
    recurse into ``to_payload`` for their fields so a nested DataFrame still
    becomes a ``"table"``), then generic JSON containers, falling back to
    ``"unsupported"`` for anything else (e.g. a ``torch.nn.Module``).
    """
    if value is None or isinstance(value, (bool, int, float)):
        return {"kind": "scalar", "value": value}

    if isinstance(value, str):
        if len(value) <= MAX_TEXT_CHARS:
            return {"kind": "scalar", "value": value}
        return {
            "kind": "text",
            "value": value[:MAX_TEXT_CHARS],
            "length": len(value),
            "truncated": True,
        }

    import pandas as pd

    if isinstance(value, pd.DataFrame):
        head = json.loads(value.head(MAX_HEAD_ROWS).to_json(orient="records"))
        return {
            "kind": "table",
            "columns": [str(c) for c in value.columns],
            "dtypes": [str(dt) for dt in value.dtypes],
            "shape": [int(value.shape[0]), int(value.shape[1])],
            "head": head,
            "truncated": bool(value.shape[0] > MAX_HEAD_ROWS),
        }

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: to_payload(getattr(value, f.name)) for f in dataclasses.fields(value)}
        return {"kind": "record", "type": type(value).__name__, "fields": fields}

    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        fields = {name: to_payload(getattr(value, name)) for name in value.__class__.model_fields}
        return {"kind": "record", "type": type(value).__name__, "fields": fields}

    if isinstance(value, (list, tuple, dict)):
        try:
            return {"kind": "json", "value": json.loads(json.dumps(value))}
        except (TypeError, ValueError):
            pass

    return {
        "kind": "unsupported",
        "type": type(value).__name__,
        "repr": repr(value)[:MAX_TEXT_CHARS],
    }
