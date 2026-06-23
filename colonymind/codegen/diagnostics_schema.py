"""
colonymind.codegen.diagnostics_schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
JSON Schema export for the ``Diagnostics`` validation result (Epic 3, Story 7).

The separate frontend canvas repo renders edge highlights and "why" tooltips
against this stable contract without importing Python. Source of truth is the
Pydantic model :class:`~colonymind.codegen.validation.Diagnostics`; this mirrors
:mod:`colonymind.ir.schema` for the IR.
"""

from __future__ import annotations

import json
from typing import Any

from colonymind.api import public_op
from colonymind.codegen.validation import Diagnostics


@public_op(name="cm.diagnostics_json_schema")
def diagnostics_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for a ``Diagnostics`` result, derived from the Pydantic model."""
    return Diagnostics.model_json_schema()


def write_diagnostics_json_schema(path: str) -> None:
    """Write the Diagnostics JSON Schema to ``path`` as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(diagnostics_json_schema(), fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "diagnostics.schema.json"
    write_diagnostics_json_schema(out)
    print(f"wrote Diagnostics JSON Schema to {out}")
