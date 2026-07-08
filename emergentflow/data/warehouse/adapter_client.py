"""
emergentflow.data.warehouse.adapter_client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``AdapterWarehouseClient`` (Epic 13 Story 3/6, ADR 0018): the effectful
``WarehouseClient`` that resolves a connection profile to live credentials
(edge-only) and dispatches to a per-dialect ``WarehouseAdapter``. Concrete
adapters (DuckDB/BigQuery/Redshift/Postgres) ship in Story 6; this client takes
them as an injected ``dialect -> adapter`` mapping, so the dispatch seam is
testable now with a fake adapter and real adapters drop in without a client change.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Mapping

import pandas as pd

from emergentflow.data.warehouse.credentials import resolve_credentials
from emergentflow.data.warehouse.profiles import ConnectionProfile, ProfileStore
from emergentflow.data.warehouse.protocol import (
    ByteScanCapExceededError,
    CostEstimate,
    QueryRequest,
    QueryResult,
    QueryTimeoutError,
    WarehouseAdapter,
    dry_run_result,
)


class NoAdapterError(RuntimeError):
    """Raised when no ``WarehouseAdapter`` is registered for a profile's dialect."""


class AdapterWarehouseClient:
    """Effectful ``WarehouseClient`` dispatching to per-dialect adapters (ADR 0018).

    Parameters
    ----------
    store: the local connection-profile store.
    adapters: mapping of dialect key -> ``WarehouseAdapter``. Real adapters are
        Story 6; inject a fake here to test the dispatch/resolution seam.
    """

    def __init__(self, store: ProfileStore, adapters: Mapping[str, WarehouseAdapter]) -> None:
        self._store = store
        self._adapters = dict(adapters)

    def _adapter_for(self, dialect: str) -> WarehouseAdapter:
        try:
            return self._adapters[dialect]
        except KeyError as exc:
            raise NoAdapterError(
                f"No warehouse adapter registered for dialect {dialect!r}. Adapters ship in "
                f"Epic 13 Story 6; registered: {', '.join(sorted(self._adapters)) or '<none>'}."
            ) from exc

    def _resolve(self, connection: str) -> tuple[ConnectionProfile, dict[str, str]]:
        profile = self._store.get(connection)  # raises UnknownConnectionError if absent
        return profile, resolve_credentials(profile)

    def _execute_with_timeout(
        self,
        adapter: WarehouseAdapter,
        request: QueryRequest,
        credentials: dict[str, str],
        timeout_s: float | None,
    ) -> QueryResult:
        if timeout_s is None:
            return adapter.execute(request, credentials)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(adapter.execute, request, credentials)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise QueryTimeoutError(timeout_s) from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def run(self, request: QueryRequest) -> QueryResult:
        if request.dry_run:
            return dry_run_result(self.dry_run(request))
        profile, credentials = self._resolve(request.connection)
        adapter = self._adapter_for(profile.dialect)
        timeout_s = profile.limits.get("timeout_s")
        result = self._execute_with_timeout(adapter, request, credentials, timeout_s)
        if (
            request.byte_scan_cap is not None
            and result.bytes_scanned is not None
            and result.bytes_scanned > request.byte_scan_cap
        ):
            raise ByteScanCapExceededError(request.byte_scan_cap, result.bytes_scanned)
        return result

    def dry_run(self, request: QueryRequest) -> CostEstimate:
        profile, credentials = self._resolve(request.connection)
        return self._adapter_for(profile.dialect).dry_run(request, credentials)

    def list_relations(
        self, connection: str, *, database: str | None = None, schema: str | None = None
    ) -> pd.DataFrame:
        profile, credentials = self._resolve(connection)
        return self._adapter_for(profile.dialect).list_relations(
            credentials, database=database, schema=schema
        )

    def describe_relation(self, connection: str, relation: str) -> pd.DataFrame:
        profile, credentials = self._resolve(connection)
        return self._adapter_for(profile.dialect).describe_relation(credentials, relation)
