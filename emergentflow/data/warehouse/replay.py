"""
emergentflow.data.warehouse.replay
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ReplayWarehouseClient`` — the pure ``WarehouseClient`` implementation (ADR
0018) used by tests and the ADR-0002 equivalence harness. Replays a recorded
``QueryResult`` keyed by the requesting ``QueryRequest.content_hash()``; never
touches a warehouse.

Fixtures are content-addressed JSON files, one per recorded result, named
``<content_hash>.json``. ``write_fixture`` is the companion writer used to seed
fixtures from a live (DuckDB-recorded or hand-built) ``QueryResult``. The frame
is serialized via pandas' Table-Schema orient so dtypes round-trip exactly,
keeping the equivalence gate value-exact.

Mirrors ``emergentflow.llm.replay`` deliberately (ADR 0018 reuses the ADR-0017
seam pattern rather than inventing a new one).
"""

from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path

import pandas as pd

from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    FixtureMissError,
    QueryRequest,
    QueryResult,
)


def _fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.json"


def _result_to_dict(result: QueryResult) -> dict:
    """Serialize a ``QueryResult`` to a JSON-native dict.

    The frame is written via ``to_json(orient="table")`` (pandas Table Schema)
    so column dtypes round-trip exactly on read. The index is reset first so a
    warehouse result's default RangeIndex does not leak into the fixture.
    """
    frame = result.df.reset_index(drop=True)
    return {
        "df": json.loads(frame.to_json(orient="table")),
        "row_count": result.row_count,
        "columns": [
            {"name": c.name, "dtype": c.dtype, "nullable": c.nullable} for c in result.columns
        ],
        "dialect": result.dialect,
        "bytes_scanned": result.bytes_scanned,
        "cost_usd": result.cost_usd,
        "truncated": result.truncated,
        "elapsed_ms": result.elapsed_ms,
    }


def _result_from_dict(payload: dict) -> QueryResult:
    """Reconstruct a ``QueryResult`` from the dict shape ``_result_to_dict`` writes."""
    frame = pd.read_json(StringIO(json.dumps(payload["df"])), orient="table").reset_index(drop=True)
    frame.index.name = None
    columns = tuple(
        ColumnSchema(name=c["name"], dtype=c["dtype"], nullable=c["nullable"])
        for c in payload["columns"]
    )
    return QueryResult(
        df=frame,
        row_count=payload["row_count"],
        columns=columns,
        dialect=payload["dialect"],
        bytes_scanned=payload["bytes_scanned"],
        cost_usd=payload["cost_usd"],
        truncated=payload["truncated"],
        elapsed_ms=payload["elapsed_ms"],
    )


def write_fixture(
    fixtures_dir: str | os.PathLike[str], request: QueryRequest, result: QueryResult
) -> Path:
    """Write *result* as a content-addressed fixture for *request*.

    Creates *fixtures_dir* if it does not exist. The fixture file is named
    ``<request.content_hash()>.json``. Returns the path written. This is the
    seeding path used by tests and any future ``--record`` tooling that captures
    a live (DuckDB-recorded) ``QueryResult``.
    """
    dir_path = Path(fixtures_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = _fixture_path(dir_path, request.content_hash())
    path.write_text(json.dumps(_result_to_dict(result), indent=2, sort_keys=True) + "\n")
    return path


class ReplayWarehouseClient:
    """A pure ``WarehouseClient`` that replays recorded ``QueryResult``s from disk.

    Structurally satisfies ``emergentflow.data.warehouse.protocol.WarehouseClient``
    for the ``run`` path (no inheritance required). Introspection replay
    (``list_relations``/``describe_relation``) and ``dry_run`` replay arrive with
    Story 7/8; for now they raise ``NotImplementedError`` so a miswired call fails
    loudly rather than silently.

    Parameters
    ----------
    fixtures_dir:
        Directory containing ``<content_hash>.json`` fixture files. The caller (a
        test, the equivalence harness) chooses this path; this class has no
        default so the library stays agnostic of where fixtures live.
    """

    def __init__(self, fixtures_dir: str | os.PathLike[str]) -> None:
        self.fixtures_dir = Path(fixtures_dir)

    def run(self, request: QueryRequest) -> QueryResult:
        """Replay the fixture recorded for *request*.

        Raises
        ------
        FixtureMissError
            If no fixture exists for ``request.content_hash()``. The message
            includes the hash and a copy-pasteable ``write_fixture(...)`` call.
        """
        content_hash = request.content_hash()
        path = _fixture_path(self.fixtures_dir, content_hash)
        if not path.exists():
            raise FixtureMissError(
                f"No recorded fixture for query request hash {content_hash!r} "
                f"(looked in {self.fixtures_dir}). To record one:\n"
                f"    from emergentflow.data.warehouse.replay import write_fixture\n"
                f"    write_fixture({str(self.fixtures_dir)!r}, request, result)  "
                f"# result is the QueryResult you want this request to replay"
            )
        payload = json.loads(path.read_text())
        return _result_from_dict(payload)

    def dry_run(self, request: QueryRequest) -> QueryResult:  # pragma: no cover - Story 8
        raise NotImplementedError("ReplayWarehouseClient.dry_run arrives with Epic 13 Story 8.")

    def list_relations(
        self, connection: str, *, database: str | None = None, schema: str | None = None
    ) -> pd.DataFrame:  # pragma: no cover - Story 7
        raise NotImplementedError(
            "ReplayWarehouseClient.list_relations arrives with Epic 13 Story 7."
        )

    def describe_relation(
        self, connection: str, relation: str
    ) -> pd.DataFrame:  # pragma: no cover - Story 7
        raise NotImplementedError(
            "ReplayWarehouseClient.describe_relation arrives with Epic 13 Story 7."
        )
