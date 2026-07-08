"""
emergentflow.data.warehouse.browser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Design-time schema-browser API (Epic 13 Story 7, ADR 0018).

Server/UI-facing functions that call an injected ``WarehouseClient`` to power
the connection manager's relation tree and the raw-SQL editor's autocomplete
(the "``df.<TAB>`` discoverability" gap). This module is deliberately **not** a
graph node and is never called from ``execute()``/``compile_to_code()`` — the
graph never re-introspects a warehouse at run time; introspection here is a
one-off, cacheable, design-time call the server makes on the analyst's behalf
while they build a query.

Thin wrappers over ``WarehouseClient.list_relations``/``describe_relation`` plus
an optional in-memory cache so repeated browsing (e.g. expanding the same
schema twice) does not re-hit the warehouse.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.data.warehouse.protocol import WarehouseClient


class SchemaBrowserCache:
    """A simple in-memory cache for design-time schema-introspection calls.

    Keyed by a tuple identifying the call (method name + arguments). The server
    constructs one instance per session (or per connection) and passes it to
    ``list_relations``/``describe_relation`` below to avoid repeat warehouse
    round-trips while an analyst browses the schema tree. Not thread-safe by
    design — matches the single-user local-server trust model the rest of this
    epic assumes.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[object, ...], pd.DataFrame] = {}

    def get(self, key: tuple[object, ...]) -> pd.DataFrame | None:
        """Return the cached frame for *key*, or ``None`` on a cache miss."""
        return self._entries.get(key)

    def set(self, key: tuple[object, ...], value: pd.DataFrame) -> None:
        """Store *value* under *key*."""
        self._entries[key] = value

    def clear(self) -> None:
        """Drop every cached entry (e.g. when a connection profile changes)."""
        self._entries.clear()


def list_relations(
    client: WarehouseClient,
    connection: str,
    *,
    database: str | None = None,
    schema: str | None = None,
    cache: SchemaBrowserCache | None = None,
) -> pd.DataFrame:
    """Return a tidy relations frame for *connection* (design-time only).

    Delegates to ``client.list_relations(...)``. When *cache* is given, a call
    with identical arguments is served from the cache instead of re-invoking the
    client; the result is stored in *cache* on a miss.
    """
    key = ("list_relations", connection, database, schema)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    df = client.list_relations(connection, database=database, schema=schema)
    if cache is not None:
        cache.set(key, df)
    return df


def describe_relation(
    client: WarehouseClient,
    connection: str,
    relation: str,
    *,
    database: str | None = None,
    schema: str | None = None,
    cache: SchemaBrowserCache | None = None,
) -> pd.DataFrame:
    """Return a tidy column-schema frame for *relation* (design-time only).

    *database*/*schema* disambiguate a *relation* name that exists in more than one
    schema — pass the values ``list_relations`` reported for the tree node the caller
    clicked. Delegates to ``client.describe_relation(...)``. When *cache* is given, a
    call with identical arguments is served from the cache instead of re-invoking the
    client; the result is stored in *cache* on a miss.
    """
    key = ("describe_relation", connection, relation, database, schema)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    df = client.describe_relation(connection, relation, database=database, schema=schema)
    if cache is not None:
        cache.set(key, df)
    return df
