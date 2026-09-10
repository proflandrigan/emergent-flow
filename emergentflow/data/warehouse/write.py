"""
emergentflow.data.warehouse.write
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ef.data.write_table`` — the single wrapper for the warehouse write path (issue #164 Gap 6).

Mirrors ``emergentflow.data.warehouse.query.query`` exactly: builds a pure
``WriteRequest`` (table + mode + connection-profile name), then delegates the one effect
to the injected ``WarehouseClient.write``. Keeping request-building in one place makes
``codegen`` and ``execute`` route identically, so the ADR-0002 equivalence holds by
construction (the ADR-0017/0018 injected-client pattern applied to a second effect).

The write itself is gated at the client edge: a connection profile whose
``write_enabled`` is false raises :class:`WriteNotEnabledError` (ADR 0018 read-only by
default). Pure aside from that single delegated effect.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.warehouse.protocol import WarehouseClient, WriteRequest

__all__ = ["write_table"]

_WRITE_MODES = ("append", "truncate", "error")


@public_op(name="ef.data.write_table")
def write_table(
    df: pd.DataFrame,
    *,
    table: str,
    connection: str,
    dialect: str,
    mode: str = "append",
    client: WarehouseClient | None = None,
) -> pd.DataFrame:
    """Materialize *df* as a warehouse table via the injected client.

    ``table`` is the target relation (optionally ``schema.table``); ``mode`` is
    ``"append"`` (default), ``"truncate"`` (delete every row, keep the table definition,
    then append -- one transaction), or ``"error"`` (refuse if the table already exists).
    ``connection`` names a connection profile; ``dialect`` is its sqlglot dialect key
    (validated, and it must match the profile's dialect). ``client`` is the injected
    ``WarehouseClient`` — passed via ``execute(graph, clients=Clients(warehouse=...))``
    or the compiled module's ``main(clients=...)``.

    Requires a connection profile with writes explicitly enabled: the read-only
    default (ADR 0018) rejects the write with a :class:`WriteNotEnabledError` naming
    the ``write_enabled = true`` setting to change. Returns *df* unchanged so the node
    stays chainable mid-graph (same pattern as ``ef.data.save_frame``). Never mutates
    ``df``.
    """
    if client is None:
        from emergentflow.data.warehouse.query import MissingWarehouseClientError

        raise MissingWarehouseClientError(
            "ef.data.write_table requires an injected WarehouseClient; pass it via "
            "execute(graph, clients=Clients(warehouse=...)) or the compiled module's "
            "main(clients=...)."
        )
    if not table or not isinstance(table, str):
        raise ValueError(f"table must be a non-empty string, got {table!r}")
    if mode not in _WRITE_MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {list(_WRITE_MODES)!r}.")
    from emergentflow.data.warehouse.query import _validate_dialect

    _validate_dialect(dialect)  # raises UnknownDialectError for a non-sqlglot key
    request = WriteRequest(
        table=table,
        dialect=dialect,
        connection=connection,
        mode=mode,
    )
    client.write(request, df)
    return df
