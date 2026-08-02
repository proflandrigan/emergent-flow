"""Export the IR JSON Schema and node catalog as static artifacts for the canvas build.

The canvas (ui/) is a pure consumer of the SDK contract (ADR 0013 Decision 3) and never imports
emergentflow. This script writes the contract artifacts the build consumes:

  ui/src/generated/ir.schema.json          -- the IR JSON Schema (drives TypeScript type generation)
  ui/src/generated/catalog.json            -- the node catalog (palette + config-panel templates)
  ui/src/generated/mutation.schema.json    -- GraphMutation JSON Schema (Epic 14 Story 4)
  ui/src/generated/session_event.schema.json -- Session SSE event JSON Schema (Epic 14 Story 4)
  ui/src/generated/validity_rules.json     -- the experiment-validity rule pack (Epic 17 Story 2)

All five are byte-identical to what the local server's GET /schema, GET /catalog,
GET /mutation-schema, GET /session-event-schema, and GET /validity-rules serve, because this
script and the server call the SAME emergentflow.server.service functions (ADR 0014 Dec. 5).

Regenerate after changing the IR models or any node's spec:
    uv run python scripts/export_ui_contracts.py
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from emergentflow.server.service import (
    get_catalog,
    get_mutation_schema,
    get_schema,
    get_session_event_schema,
    get_validity_rules,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATED_DIR = REPO_ROOT / "ui" / "src" / "generated"


def _write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def export_ui_contracts(generated_dir: pathlib.Path = GENERATED_DIR) -> None:
    """Write ir.schema.json, catalog.json, mutation.schema.json,
    session_event.schema.json, and validity_rules.json into *generated_dir*."""
    _write_json(generated_dir / "ir.schema.json", get_schema())
    _write_json(generated_dir / "catalog.json", get_catalog())
    _write_json(generated_dir / "mutation.schema.json", get_mutation_schema())
    _write_json(generated_dir / "session_event.schema.json", get_session_event_schema())
    _write_json(generated_dir / "validity_rules.json", get_validity_rules())


if __name__ == "__main__":
    export_ui_contracts()
    print(f"wrote UI contracts to {GENERATED_DIR}")
