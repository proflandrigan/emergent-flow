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

import hashlib
import json
import os
from io import StringIO
from pathlib import Path

import pandas as pd

from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    CostEstimate,
    FixtureMissError,
    QueryRequest,
    QueryResult,
    dry_run_result,
    enforce_byte_scan_cap,
)


def _fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.json"


def _dry_run_fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.dryrun.json"


def _estimate_to_dict(estimate: CostEstimate) -> dict:
    return {
        "dialect": estimate.dialect,
        "bytes_scanned": estimate.bytes_scanned,
        "estimated_rows": estimate.estimated_rows,
        "cost_usd": estimate.cost_usd,
    }


def _estimate_from_dict(payload: dict) -> CostEstimate:
    return CostEstimate(
        dialect=payload["dialect"],
        bytes_scanned=payload["bytes_scanned"],
        estimated_rows=payload["estimated_rows"],
        cost_usd=payload["cost_usd"],
    )


def _introspection_hash(**payload: str | None) -> str:
    """Return a stable sha256 hex digest identifying one introspection call.

    Mirrors ``QueryRequest.content_hash()`` (sorted-keys JSON, sha256) but for
    the ``list_relations``/``describe_relation`` argument shape, which has no
    dataclass of its own. ``payload`` must include a ``"method"`` key
    (``"list_relations"`` or ``"describe_relation"``) so the two call kinds never
    collide even with otherwise-identical arguments.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _relations_fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.relations.json"


def _describe_fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.describe.json"


def _frame_to_dict(df: pd.DataFrame) -> dict:
    """Serialize a tidy schema DataFrame via pandas Table Schema orient.

    Mirrors the ``df`` handling inside ``_result_to_dict`` so column dtypes
    round-trip exactly and the default RangeIndex never leaks into the fixture.
    """
    return json.loads(df.reset_index(drop=True).to_json(orient="table"))


def _frame_from_dict(payload: dict) -> pd.DataFrame:
    """Reconstruct a tidy DataFrame from the dict shape ``_frame_to_dict`` writes."""
    frame = pd.read_json(StringIO(json.dumps(payload)), orient="table").reset_index(drop=True)
    frame.index.name = None
    return frame


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


def write_dry_run_fixture(
    fixtures_dir: str | os.PathLike[str], request: QueryRequest, estimate: CostEstimate
) -> Path:
    """Write *estimate* as the recorded ``dry_run`` fixture for *request*.

    Creates *fixtures_dir* if it does not exist. The fixture file is named
    ``<request.content_hash()>.dryrun.json`` — note ``QueryRequest.content_hash()``
    already includes the ``dry_run`` field, so a dry-run request and the
    equivalent live-run request never collide on the same hash even though they
    also differ by the ``.dryrun`` filename suffix.
    """
    dir_path = Path(fixtures_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = _dry_run_fixture_path(dir_path, request.content_hash())
    path.write_text(json.dumps(_estimate_to_dict(estimate), indent=2, sort_keys=True) + "\n")
    return path


def write_relations_fixture(
    fixtures_dir: str | os.PathLike[str],
    connection: str,
    df: pd.DataFrame,
    *,
    database: str | None = None,
    schema: str | None = None,
) -> Path:
    """Write *df* as the recorded ``list_relations`` fixture for these arguments.

    Creates *fixtures_dir* if it does not exist. Companion writer to
    ``write_fixture``, for the introspection path (Epic 13 Story 7).
    """
    dir_path = Path(fixtures_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    content_hash = _introspection_hash(
        method="list_relations", connection=connection, database=database, schema=schema
    )
    path = _relations_fixture_path(dir_path, content_hash)
    path.write_text(json.dumps(_frame_to_dict(df), indent=2, sort_keys=True) + "\n")
    return path


def write_describe_fixture(
    fixtures_dir: str | os.PathLike[str],
    connection: str,
    relation: str,
    df: pd.DataFrame,
    *,
    database: str | None = None,
    schema: str | None = None,
) -> Path:
    """Write *df* as the recorded ``describe_relation`` fixture for these arguments.

    Creates *fixtures_dir* if it does not exist. Companion writer to
    ``write_fixture``, for the introspection path (Epic 13 Story 7).
    """
    dir_path = Path(fixtures_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    content_hash = _introspection_hash(
        method="describe_relation",
        connection=connection,
        relation=relation,
        database=database,
        schema=schema,
    )
    path = _describe_fixture_path(dir_path, content_hash)
    path.write_text(json.dumps(_frame_to_dict(df), indent=2, sort_keys=True) + "\n")
    return path


class ReplayWarehouseClient:
    """A pure ``WarehouseClient`` that replays recorded ``QueryResult``s from disk.

    Structurally satisfies ``emergentflow.data.warehouse.protocol.WarehouseClient``
    for the ``run``, ``dry_run``, ``list_relations``, and ``describe_relation``
    paths — every method replays a content-addressed fixture; none construct a
    live connection.

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

        When ``request.dry_run`` is True, delegates to ``self.dry_run(request)``
        and wraps the replayed ``CostEstimate`` as an empty ``QueryResult``
        instead of replaying a query-result fixture (Epic 13 Story 8).

        Raises
        ------
        FixtureMissError
            If no fixture exists for ``request.content_hash()``. The message
            includes the hash and a copy-pasteable ``write_fixture(...)`` call.
        ByteScanCapExceededError
            If the replayed fixture's ``bytes_scanned`` exceeds
            ``request.byte_scan_cap`` — the cap is enforced identically whether
            the result came from a live adapter or a recorded fixture.
        """
        if request.dry_run:
            return dry_run_result(self.dry_run(request))
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
        result = _result_from_dict(payload)
        enforce_byte_scan_cap(request, result)
        return result

    def dry_run(self, request: QueryRequest) -> CostEstimate:
        """Replay the fixture recorded for this ``dry_run`` call.

        Raises
        ------
        FixtureMissError
            If no fixture exists for ``request.content_hash()``. The message
            includes the hash and a copy-pasteable ``write_dry_run_fixture(...)`` call.
        """
        content_hash = request.content_hash()
        path = _dry_run_fixture_path(self.fixtures_dir, content_hash)
        if not path.exists():
            raise FixtureMissError(
                f"No recorded dry-run fixture for query request hash {content_hash!r} "
                f"(looked in {self.fixtures_dir}). To record one:\n"
                f"    from emergentflow.data.warehouse.replay import write_dry_run_fixture\n"
                f"    write_dry_run_fixture({str(self.fixtures_dir)!r}, request, estimate)  "
                f"# estimate is the CostEstimate you want this request to replay"
            )
        payload = json.loads(path.read_text())
        return _estimate_from_dict(payload)

    def list_relations(
        self, connection: str, *, database: str | None = None, schema: str | None = None
    ) -> pd.DataFrame:
        """Replay the fixture recorded for this ``list_relations`` call.

        Raises
        ------
        FixtureMissError
            If no fixture exists for this call's introspection hash. The message
            includes the hash and a copy-pasteable ``write_relations_fixture(...)`` call.
        """
        content_hash = _introspection_hash(
            method="list_relations", connection=connection, database=database, schema=schema
        )
        path = _relations_fixture_path(self.fixtures_dir, content_hash)
        if not path.exists():
            raise FixtureMissError(
                f"No recorded fixture for list_relations call hash {content_hash!r} "
                f"(looked in {self.fixtures_dir}). To record one:\n"
                f"    from emergentflow.data.warehouse.replay import write_relations_fixture\n"
                f"    write_relations_fixture({str(self.fixtures_dir)!r}, {connection!r}, df, "
                f"database={database!r}, schema={schema!r})  "
                f"# df is the DataFrame you want this call to replay"
            )
        payload = json.loads(path.read_text())
        return _frame_from_dict(payload)

    def describe_relation(
        self,
        connection: str,
        relation: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        """Replay the fixture recorded for this ``describe_relation`` call.

        Raises
        ------
        FixtureMissError
            If no fixture exists for this call's introspection hash. The message
            includes the hash and a copy-pasteable ``write_describe_fixture(...)`` call.
        """
        content_hash = _introspection_hash(
            method="describe_relation",
            connection=connection,
            relation=relation,
            database=database,
            schema=schema,
        )
        path = _describe_fixture_path(self.fixtures_dir, content_hash)
        if not path.exists():
            raise FixtureMissError(
                f"No recorded fixture for describe_relation call hash {content_hash!r} "
                f"(looked in {self.fixtures_dir}). To record one:\n"
                f"    from emergentflow.data.warehouse.replay import write_describe_fixture\n"
                f"    write_describe_fixture({str(self.fixtures_dir)!r}, {connection!r}, "
                f"{relation!r}, df, database={database!r}, schema={schema!r})  "
                f"# df is the DataFrame you want this call to replay"
            )
        payload = json.loads(path.read_text())
        return _frame_from_dict(payload)
