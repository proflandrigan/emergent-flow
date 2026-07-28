"""Assert every loader node's compiled source threads the schema-on-load contract
params (``expect_columns`` / ``expect_dtypes``) and bumped its ``version``
(Epic 16 Story 4)."""

from __future__ import annotations

import ast

import pytest

from emergentflow.nodes.examples.load_csv import LoadCsv
from emergentflow.nodes.examples.load_excel import LoadExcel
from emergentflow.nodes.examples.load_google_sheet import LoadGoogleSheet
from emergentflow.nodes.examples.load_json import LoadJson
from emergentflow.nodes.examples.load_parquet import LoadParquet

LOADER_NODE_CLASSES = [
    LoadCsv,
    LoadParquet,
    LoadJson,
    LoadExcel,
    LoadGoogleSheet,
]


def _instantiate(cls):
    if cls is LoadGoogleSheet:
        return cls().instantiate(spreadsheet_id="abc123")
    return cls().instantiate(path="data.file")


@pytest.mark.parametrize("cls", LOADER_NODE_CLASSES, ids=lambda c: c.type)
def test_loader_node_compiled_source_has_schema_params(cls) -> None:
    defn = cls()
    node = _instantiate(cls)
    frag = defn.preview(node)
    source = frag.render()

    assert "expect_columns=" in source
    assert "expect_dtypes=" in source
    ast.parse(source)


@pytest.mark.parametrize("cls", LOADER_NODE_CLASSES, ids=lambda c: c.type)
def test_loader_node_version_bumped(cls) -> None:
    assert cls.version >= 2
