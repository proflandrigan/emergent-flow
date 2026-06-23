"""Tests for the Story 7 portable rules artifact and Diagnostics schema exports."""

from __future__ import annotations

import json
import pathlib

from colonymind.codegen.diagnostics_schema import (
    diagnostics_json_schema,
    write_diagnostics_json_schema,
)
from colonymind.ir.graph import CURRENT_SCHEMA_VERSION
from colonymind.types.rules_artifact import build_rules_artifact, write_rules_artifact

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_build_rules_artifact_keys():
    assert set(build_rules_artifact()) == {
        "version",
        "types",
        "top",
        "subtypes",
        "semantics",
    }


def test_build_rules_artifact_version_matches_schema():
    assert build_rules_artifact()["version"] == CURRENT_SCHEMA_VERSION


def test_build_rules_artifact_semantics():
    assert build_rules_artifact()["semantics"] == {
        "wildcard": "any",
        "exact": True,
        "subtype": True,
        "unknown": "warn",
    }


def test_build_rules_artifact_top_and_types():
    artifact = build_rules_artifact()
    assert artifact["top"] == "any"
    assert "DataFrame" in artifact["types"]
    assert "Tensor" in artifact["types"]
    assert "any" in artifact["types"]


def test_build_rules_artifact_deterministic():
    assert build_rules_artifact() == build_rules_artifact()


def test_write_rules_artifact_round_trips(tmp_path: pathlib.Path):
    path = tmp_path / "rules.json"
    write_rules_artifact(str(path))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data == build_rules_artifact()
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_diagnostics_json_schema_is_dict():
    assert isinstance(diagnostics_json_schema(), dict)


def test_write_diagnostics_json_schema_round_trips(tmp_path: pathlib.Path):
    path = tmp_path / "d.json"
    write_diagnostics_json_schema(str(path))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data == diagnostics_json_schema()


def test_committed_rules_artifact_not_stale():
    committed = REPO_ROOT / "schema" / "rules.json"
    with open(committed, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data == build_rules_artifact(), (
        "Committed rules artifact is stale. "
        "Run `python -m colonymind.types.rules_artifact schema/rules.json` "
        "to regenerate."
    )


def test_committed_diagnostics_schema_not_stale():
    committed = REPO_ROOT / "schema" / "diagnostics.schema.json"
    with open(committed, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data == diagnostics_json_schema(), (
        "Committed diagnostics schema is stale. "
        "Run `python -m colonymind.codegen.diagnostics_schema "
        "schema/diagnostics.schema.json` to regenerate."
    )
