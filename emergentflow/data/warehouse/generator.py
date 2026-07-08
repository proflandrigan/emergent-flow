"""
emergentflow.data.warehouse.generator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A pure generator mapping the curated warehouse connector allow-list to
catalog-entry dicts (Epic 13 Story 6 — the ``emergentflow.ml.generator``
analog for warehouse connectors).

Turns the connector registry into JSON-native data the connection-manager UI
can render with zero per-warehouse UI code: no I/O, no global state,
deterministic given the same input list.
"""

from __future__ import annotations

from typing import Any

_CONNECTORS: list[dict[str, Any]] = [
    {
        "dialect": "duckdb",
        "label": "DuckDB",
        "extra": None,
        "adapter": "emergentflow.data.warehouse.adapters.duckdb_adapter.DuckDBAdapter",
        "description": "In-process SQL engine for local parquet, CSV, and DuckDB files.",
        "auth_schema": {
            "path": {
                "type": "str",
                "required": False,
                "help": "Path to a .duckdb file; defaults to :memory:.",
            },
        },
    },
    {
        "dialect": "bigquery",
        "label": "BigQuery",
        "extra": "emergentflow[bigquery]",
        "adapter": "emergentflow.data.warehouse.adapters.bigquery_adapter.BigQueryAdapter",
        "description": "Google BigQuery data warehouse.",
        "auth_schema": {
            "project": {
                "type": "str",
                "required": True,
                "help": "GCP project ID.",
            },
            "credentials_json": {
                "type": "str",
                "required": False,
                "help": "Path to a service-account JSON key file.",
            },
        },
    },
    {
        "dialect": "redshift",
        "label": "Redshift",
        "extra": "emergentflow[redshift]",
        "adapter": "emergentflow.data.warehouse.adapters.redshift_adapter.RedshiftAdapter",
        "description": "Amazon Redshift data warehouse.",
        "auth_schema": {
            "host": {"type": "str", "required": True, "help": "Redshift cluster endpoint."},
            "port": {"type": "str", "required": False, "help": "Port (default 5439)."},
            "database": {"type": "str", "required": True, "help": "Database name."},
            "user": {"type": "str", "required": True, "help": "Database user."},
            "password": {"type": "str", "required": True, "help": "Database password."},
        },
    },
    {
        "dialect": "postgres",
        "label": "PostgreSQL",
        "extra": "emergentflow[postgres]",
        "adapter": "emergentflow.data.warehouse.adapters.postgres_adapter.PostgresAdapter",
        "description": "PostgreSQL database.",
        "auth_schema": {
            "host": {"type": "str", "required": True, "help": "Database host."},
            "port": {"type": "str", "required": False, "help": "Port (default 5432)."},
            "database": {"type": "str", "required": True, "help": "Database name."},
            "user": {"type": "str", "required": True, "help": "Database user."},
            "password": {"type": "str", "required": True, "help": "Database password."},
        },
    },
]


def known_connector_dialects() -> list[str]:
    """Return the sorted list of curated connector dialect keys."""
    return sorted(c["dialect"] for c in _CONNECTORS)


def generate_connector_catalog_entries() -> list[dict[str, Any]]:
    """Map the curated connector allow-list to JSON-native catalog-entry dicts.

    Pure: output depends only on the module-level ``_CONNECTORS`` list.
    Sorted by ``dialect`` for stable golden output.
    """
    return sorted(_CONNECTORS, key=lambda c: c["dialect"])
