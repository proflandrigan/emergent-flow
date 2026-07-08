"""Tests for ``emergentflow.data.warehouse.browser`` (Epic 13 Story 7)."""

from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from emergentflow.data.warehouse.browser import (
    SchemaBrowserCache,
    describe_relation,
    list_relations,
)


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def list_relations(self, connection, *, database=None, schema=None):
        self.calls.append(("list_relations", connection, database, schema))
        return pd.DataFrame({"table": ["t1"]})

    def describe_relation(self, connection, relation):
        self.calls.append(("describe_relation", connection, relation))
        return pd.DataFrame({"column": ["c1"]})


def test_list_relations_without_cache_always_calls_client():
    client = _FakeClient()
    list_relations(client, "warehouse_prod", schema="public")
    list_relations(client, "warehouse_prod", schema="public")
    assert len(client.calls) == 2


def test_list_relations_with_cache_calls_client_once():
    client = _FakeClient()
    cache = SchemaBrowserCache()
    df1 = list_relations(client, "warehouse_prod", schema="public", cache=cache)
    df2 = list_relations(client, "warehouse_prod", schema="public", cache=cache)
    assert len(client.calls) == 1
    assert_frame_equal(df1, df2)


def test_describe_relation_with_cache_calls_client_once():
    client = _FakeClient()
    cache = SchemaBrowserCache()
    df1 = describe_relation(client, "warehouse_prod", "t1", cache=cache)
    df2 = describe_relation(client, "warehouse_prod", "t1", cache=cache)
    assert len(client.calls) == 1
    assert_frame_equal(df1, df2)


def test_cache_discriminates_by_arguments():
    client = _FakeClient()
    cache = SchemaBrowserCache()
    list_relations(client, "warehouse_prod", schema="public", cache=cache)
    list_relations(client, "warehouse_prod", schema="other", cache=cache)
    assert len(client.calls) == 2


def test_cache_discriminates_list_relations_from_describe_relation():
    client = _FakeClient()
    cache = SchemaBrowserCache()
    list_relations(client, "warehouse_prod", schema="public", cache=cache)
    describe_relation(client, "warehouse_prod", "public", cache=cache)
    assert len(client.calls) == 2


def test_cache_clear_forces_client_recall():
    client = _FakeClient()
    cache = SchemaBrowserCache()
    list_relations(client, "warehouse_prod", schema="public", cache=cache)
    cache.clear()
    list_relations(client, "warehouse_prod", schema="public", cache=cache)
    assert len(client.calls) == 2
