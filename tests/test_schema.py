"""Tests for colonymind.ir.schema — JSON Schema export."""
from __future__ import annotations

import json
import pathlib

import pytest

from colonymind.ir.schema import ir_json_schema, write_ir_json_schema


def _graph_properties(schema: dict) -> dict:
    """Locate the Graph object's ``properties`` in a possibly-recursive schema.

    Graph is self-referential (Graph -> Node.subgraph -> Graph), so Pydantic emits
    the spec-compliant shape where the root is a ``$ref`` into ``$defs`` rather than
    carrying ``properties`` at the top level. Resolve either form.
    """
    if "properties" in schema:
        return schema["properties"]
    ref = schema.get("$ref", "")
    assert ref.startswith("#/$defs/"), f"unexpected schema root: {schema!r}"
    name = ref.rsplit("/", 1)[-1]
    return schema["$defs"][name]["properties"]


def test_ir_json_schema_returns_dict():
    schema = ir_json_schema()
    assert isinstance(schema, dict)


def test_ir_json_schema_has_graph_properties():
    schema = ir_json_schema()
    # Valid JSON Schema for a recursive model: root is a $ref into $defs.
    assert "$defs" in schema and ("properties" in schema or "$ref" in schema)
    assert _graph_properties(schema), "Graph definition must expose properties"


@pytest.mark.parametrize("prop", ["schema_version", "paradigm", "nodes", "edges"])
def test_ir_json_schema_required_properties_present(prop: str):
    properties = _graph_properties(ir_json_schema())
    assert prop in properties, f"Expected '{prop}' to be present in Graph schema properties"


def test_write_ir_json_schema_creates_valid_json(tmp_path: pathlib.Path):
    out = tmp_path / "ir.schema.json"
    write_ir_json_schema(str(out))

    assert out.exists(), "write_ir_json_schema should create the output file"

    with open(out, encoding="utf-8") as fh:
        loaded = json.load(fh)

    assert loaded == ir_json_schema(), (
        "File written by write_ir_json_schema should round-trip to an equal dict"
    )


def test_write_ir_json_schema_ends_with_newline(tmp_path: pathlib.Path):
    out = tmp_path / "ir.schema.json"
    write_ir_json_schema(str(out))
    content = out.read_bytes()
    assert content.endswith(b"\n"), "Schema file should end with a newline"
