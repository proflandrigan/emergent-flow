"""Tests for the Story 2 node-catalog artifact (cm.export_catalog)."""

from __future__ import annotations

import pytest

from colonymind.nodes.catalog import CATALOG_VERSION, export_catalog
from colonymind.nodes.examples import (
    Anova,
    GenerateHtmlSummary,
    ImputeMissing,
    LoadCsv,
    LoadJson,
    LoadParquet,
    LoadSample,
    NnLinear,
    NnModule,
    NnReLU,
    TrainClassifier,
)
from colonymind.nodes.registry import NodeRegistry

REFERENCE_NODES = [
    LoadCsv,
    LoadParquet,
    LoadJson,
    LoadSample,
    ImputeMissing,
    Anova,
    TrainClassifier,
    GenerateHtmlSummary,
    NnLinear,
    NnReLU,
    NnModule,
]

_NODE_KEYS = {
    "type",
    "version",
    "family",
    "label",
    "category",
    "description",
    "paradigm",
    "ports",
    "params",
}

_PARAM_KEYS = {"name", "type_token", "default", "required", "label", "help", "hints"}


@pytest.fixture
def ref_registry() -> NodeRegistry:
    reg = NodeRegistry()
    for cls in REFERENCE_NODES:
        reg.register(cls)
    return reg


def test_catalog_version_constant():
    assert CATALOG_VERSION == 1


def test_top_level_keys(ref_registry: NodeRegistry):
    assert set(export_catalog(ref_registry)) == {"catalog_version", "nodes"}


def test_version_in_artifact(ref_registry: NodeRegistry):
    assert export_catalog(ref_registry)["catalog_version"] == CATALOG_VERSION


def test_nodes_sorted_by_type(ref_registry: NodeRegistry):
    types = [node["type"] for node in export_catalog(ref_registry)["nodes"]]
    assert types == sorted(types)


def test_deterministic(ref_registry: NodeRegistry):
    assert export_catalog(ref_registry) == export_catalog(ref_registry)


def test_node_entry_keys(ref_registry: NodeRegistry):
    for node in export_catalog(ref_registry)["nodes"]:
        assert set(node) >= _NODE_KEYS


def test_every_node_has_palette_metadata(ref_registry: NodeRegistry):
    for node in export_catalog(ref_registry)["nodes"]:
        assert node["category"].strip()
        assert node["description"].strip()


def test_param_entries_are_jsonable_and_shaped(ref_registry: NodeRegistry):
    for node in export_catalog(ref_registry)["nodes"]:
        for param in node["params"]:
            assert set(param) >= _PARAM_KEYS


def test_catalog_golden(ref_registry: NodeRegistry, snapshot) -> None:
    assert export_catalog(ref_registry) == snapshot


def test_export_catalog_uses_default_registry():
    artifact = export_catalog()
    assert artifact["catalog_version"] == CATALOG_VERSION
    assert artifact["nodes"]
    types = [node["type"] for node in artifact["nodes"]]
    assert "data.load_csv" in types
