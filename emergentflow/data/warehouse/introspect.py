"""
emergentflow.data.warehouse.introspect
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ef.data.describe_relation`` — the wrapper the ``data.describe_relation`` node's
``execute``/``codegen`` both route through (Epic 13 Story 7). Delegates the single
effect to the injected ``WarehouseClient.describe_relation``. Mirrors
``ef.data.query`` (``query.py``) for the introspection path — keeping the
delegation in one wrapper function is what makes ``codegen`` and ``execute``
route identically, so the ADR-0002 equivalence holds by construction.

Pure aside from the single delegated effect ``client.describe_relation(...)``.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.warehouse.protocol import WarehouseClient
from emergentflow.data.warehouse.query import MissingWarehouseClientError

__all__ = ["describe_relation"]


@public_op(name="ef.data.describe_relation")
def describe_relation(
    *,
    connection: str,
    relation: str,
    client: WarehouseClient | None,
    database: str | None = None,
    schema: str | None = None,
) -> pd.DataFrame:
    """Return a tidy column-schema frame for *relation* under *connection*.

    *database*/*schema* disambiguate a *relation* name that exists in more than one
    schema. Pure aside from the single delegated effect
    ``client.describe_relation(connection, relation, database=database, schema=schema)``.

    Raises
    ------
    MissingWarehouseClientError
        If *client* is ``None``.
    """
    if client is None:
        raise MissingWarehouseClientError(
            "ef.data.describe_relation requires an injected WarehouseClient; pass it via "
            "execute(graph, clients=Clients(warehouse=...)) or the compiled module's "
            "main(clients=...)."
        )
    return client.describe_relation(connection, relation, database=database, schema=schema)
