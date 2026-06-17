"""JSON Schema export for the Colony Mind IR (source of truth: the Pydantic models)."""

from __future__ import annotations

import json
from typing import Any

from .graph import Graph


def ir_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for a serialized IR Graph, derived from the Pydantic models."""
    return Graph.model_json_schema()


def write_ir_json_schema(path: str) -> None:
    """Write the IR JSON Schema to ``path`` as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ir_json_schema(), fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "ir.schema.json"
    write_ir_json_schema(out)
    print(f"wrote IR JSON Schema to {out}")
