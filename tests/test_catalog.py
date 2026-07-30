"""Tests for the Story 2 node-catalog artifact (ef.export_catalog)."""

from __future__ import annotations

import pytest

from emergentflow.nodes.catalog import CATALOG_VERSION, export_catalog
from emergentflow.nodes.examples import (
    Anova,
    CastTypes,
    Correlation,
    Describe,
    DropMissing,
    Evaluate,
    FilterRows,
    GenerateHtmlSummary,
    ImputeMissing,
    LlmCall,
    LoadCsv,
    LoadExcel,
    LoadGoogleSheet,
    LoadJson,
    LoadParquet,
    LoadSample,
    NnLinear,
    NnModule,
    NnReLU,
    Predict,
    QueryBuilder,
    SelectColumns,
    SqlQuery,
    TrainClassifier,
    TrainRandomForest,
    TrainRegressor,
    TrainTestSplit,
    TTest,
    VizPlot,
)
from emergentflow.nodes.registry import NodeRegistry

REFERENCE_NODES = [
    LoadCsv,
    LoadExcel,
    LoadGoogleSheet,
    LoadParquet,
    LoadJson,
    LoadSample,
    ImputeMissing,
    DropMissing,
    SelectColumns,
    CastTypes,
    FilterRows,
    Anova,
    Correlation,
    Describe,
    TTest,
    TrainClassifier,
    TrainRandomForest,
    TrainRegressor,
    TrainTestSplit,
    Evaluate,
    Predict,
    GenerateHtmlSummary,
    NnLinear,
    NnReLU,
    NnModule,
    VizPlot,
    SqlQuery,
    QueryBuilder,
    LlmCall,
]

_NODE_KEYS = {
    "type",
    "version",
    "family",
    "label",
    "category",
    "description",
    "keywords",
    "paradigm",
    "advisor_persona",
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
    assert CATALOG_VERSION == 6


def test_top_level_keys(ref_registry: NodeRegistry):
    assert set(export_catalog(ref_registry)) == {
        "catalog_version",
        "nodes",
        "estimators",
        "charts",
        "recommenders",
        "connectors",
    }


def test_version_in_artifact(ref_registry: NodeRegistry):
    assert export_catalog(ref_registry)["catalog_version"] == CATALOG_VERSION


def test_nodes_sorted_by_type(ref_registry: NodeRegistry):
    types = [node["type"] for node in export_catalog(ref_registry)["nodes"]]
    assert types == sorted(types)


def test_estimators_present_and_sorted(ref_registry: NodeRegistry):
    estimators = export_catalog(ref_registry)["estimators"]
    assert estimators  # the seed catalog is non-empty
    keys = [e["key"] for e in estimators]
    assert keys == sorted(keys)
    for entry in estimators:
        assert set(entry) >= {
            "key",
            "node_type",
            "archetype",
            "task",
            "label",
            "category",
            "description",
            "import_path",
            "params",
        }


def test_charts_present_and_sorted(ref_registry: NodeRegistry):
    charts = export_catalog(ref_registry)["charts"]
    assert charts  # the curated catalog is non-empty
    keys = [c["key"] for c in charts]
    assert keys == sorted(keys)
    for entry in charts:
        assert set(entry) >= {
            "key",
            "node_type",
            "label",
            "category",
            "description",
            "px_function",
            "encodings",
            "options",
        }


def test_connectors_present_and_sorted(ref_registry: NodeRegistry):
    connectors = export_catalog(ref_registry)["connectors"]
    assert connectors
    dialects = [c["dialect"] for c in connectors]
    assert dialects == sorted(dialects)
    for entry in connectors:
        assert set(entry) >= {
            "dialect",
            "label",
            "extra",
            "adapter",
            "description",
            "auth_schema",
        }


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


def test_every_node_has_a_keywords_list():
    for node in export_catalog()["nodes"]:
        assert "keywords" in node
        assert isinstance(node["keywords"], list)


def test_keywords_surface_on_reshape_and_explode_nodes():
    """issue #99: the reshape verbs (melt/pivot/...) must be findable in the catalog."""
    by_type = {node["type"]: node for node in export_catalog()["nodes"]}
    reshape = by_type["clean.reshape"]
    assert "melt" in reshape["keywords"]
    assert "pivot" in reshape["keywords"]
    explode = by_type["clean.explode_lists"]
    assert "explode" in explode["keywords"]
    assert "unnest" in explode["keywords"]
