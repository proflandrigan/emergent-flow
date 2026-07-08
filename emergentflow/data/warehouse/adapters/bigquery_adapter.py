"""
emergentflow.data.warehouse.adapters.bigquery_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BigQuery ``WarehouseAdapter`` (Epic 13 Story 6, ADR 0018): optional cloud
adapter behind the ``[bigquery]`` extra. Uses ``google-cloud-bigquery``.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import pandas as pd

from emergentflow.data.warehouse.protocol import (
    RELATION_SCHEMA_COLUMNS,
    ColumnSchema,
    CostEstimate,
    MissingDriverError,
    QueryRequest,
    QueryResult,
)

try:
    from google.cloud import bigquery as _bq
except ImportError:
    _bq = None

_EXTRA = "emergentflow[bigquery]"


def _require_driver() -> None:
    if _bq is None:
        raise MissingDriverError(_EXTRA)


class BigQueryAdapter:
    """A ``WarehouseAdapter`` for Google BigQuery.

    Attributes
    ----------
    dialect: always ``"bigquery"``.
    """

    dialect: str = "bigquery"

    def _client(self, credentials: Mapping[str, str]) -> _bq.Client:
        """Build a BigQuery ``Client`` from resolved credentials."""
        _require_driver()
        project = credentials.get("project")
        credentials_json = credentials.get("credentials_json")
        if credentials_json:
            bq_credentials = _bq.Client.from_service_account_json(credentials_json)
            return _bq.Client(project=project, credentials=bq_credentials.credentials)
        return _bq.Client(project=project)

    def execute(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> QueryResult:
        _require_driver()
        start = time.monotonic()
        client = self._client(credentials)
        job_config = _bq.QueryJobConfig()
        if request.byte_scan_cap is not None:
            job_config.maximum_bytes_billed = request.byte_scan_cap
        query_job = client.query(request.sql, job_config=job_config)
        df = query_job.to_dataframe()
        elapsed_ms = (time.monotonic() - start) * 1000

        truncated = False
        if request.max_rows is not None and len(df) >= request.max_rows:
            df = df.head(request.max_rows)
            truncated = True

        bytes_scanned = query_job.total_bytes_processed

        columns = tuple(
            ColumnSchema(
                name=col,
                dtype=str(df[col].dtype),
                nullable=bool(df[col].isna().any()),
            )
            for col in df.columns
        )
        return QueryResult(
            df=df,
            row_count=len(df),
            columns=columns,
            dialect="bigquery",
            truncated=truncated,
            elapsed_ms=elapsed_ms,
            bytes_scanned=bytes_scanned,
        )

    def dry_run(
        self,
        request: QueryRequest,
        credentials: Mapping[str, str],
    ) -> CostEstimate:
        _require_driver()
        client = self._client(credentials)
        job_config = _bq.QueryJobConfig(dry_run=True, use_query_cache=False)
        query_job = client.query(request.sql, job_config=job_config)
        return CostEstimate(
            dialect="bigquery",
            bytes_scanned=query_job.total_bytes_processed,
            estimated_rows=None,
        )

    def list_relations(
        self,
        credentials: Mapping[str, str],
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        _require_driver()
        client = self._client(credentials)
        project = credentials.get("project", client.project)
        dataset_filter = schema

        if dataset_filter:
            datasets = [_bq.DatasetReference(project, dataset_filter)]
        else:
            datasets = [
                _bq.DatasetReference(project, ds.dataset_id)
                for ds in client.list_datasets(project=project)
            ]

        rows = []
        for ds_ref in datasets:
            for table in client.list_tables(ds_ref):
                rows.append(
                    {
                        "database": project,
                        "schema": ds_ref.dataset_id,
                        "table": table.table_id,
                        "column": None,
                        "data_type": None,
                        "nullable": None,
                    }
                )
        df = pd.DataFrame(rows, columns=list(RELATION_SCHEMA_COLUMNS))
        return df.sort_values(["database", "schema", "table"]).reset_index(drop=True)

    def describe_relation(
        self,
        credentials: Mapping[str, str],
        relation: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> pd.DataFrame:
        _require_driver()
        client = self._client(credentials)
        if schema:
            project = database or credentials.get("project", client.project)
            table_ref = client.get_table(_bq.DatasetReference(project, schema).table(relation))
        else:
            table_ref = client.get_table(relation)
        rows = []
        for field in table_ref.schema:
            rows.append(
                {
                    "database": table_ref.project,
                    "schema": table_ref.dataset_id,
                    "table": table_ref.table_id,
                    "column": field.name,
                    "data_type": field.field_type,
                    "nullable": field.mode != "REQUIRED",
                }
            )
        return pd.DataFrame(rows, columns=list(RELATION_SCHEMA_COLUMNS))
