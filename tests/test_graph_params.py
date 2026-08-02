"""Tests for graph-level parameters (issue #116).

Covers the IR model (``Graph.params``, ``Param.ref``/``Param.description``), the schema v2
migration, ref resolution/materialization, validation diagnostics, codegen (``main(**params)``),
``ef.execute(..., params=)``, reproducibility capture, the CLI ``--param`` flag, and the server
``/execute`` passthrough.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from emergentflow.codegen.compiler import _assemble, compile_to_code
from emergentflow.codegen.errors import GraphValidationError
from emergentflow.codegen.executor import execute
from emergentflow.codegen.params import GraphParamError, materialize_graph, resolve_graph_params
from emergentflow.codegen.validation import validate
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import CURRENT_SCHEMA_VERSION, Graph
from emergentflow.ir.node import Node
from emergentflow.ir.params import Param
from emergentflow.ir.port import Port
from emergentflow.ir.serialize import deserialize_graph
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import ParamSpec, PortSpec, ValidationHints
from emergentflow.research.reproducibility import capture_run


@register
class _GraphParamSink(NodeDefinition):
    """Test fixture: emits its ref'd param's resolved value unchanged."""

    type = "test.graph_param_sink"
    family = "test"
    label = "Graph Param Sink"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="int")]
    params = [
        ParamSpec(
            name="value",
            type_token="int",
            hints=ValidationHints(ref_supported=True),
        ),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.param_expr('value')}")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": node.params[0].value}


@register
class _GraphParamPlain(NodeDefinition):
    """Test fixture: a param that does NOT support refs (no ``ref_supported`` hint)."""

    type = "test.graph_param_plain"
    family = "test"
    label = "Graph Param Plain"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="int")]
    params = [ParamSpec(name="plain", type_token="str", default="")]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = 1")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": 1}


def _sink_node(*, ref: str | None = None) -> Node:
    return Node(
        id="n",
        type=_GraphParamSink.type,
        label=_GraphParamSink.label,
        ports=[Port(id="n-out", name="out", direction=Direction.OUT, data_type="int")],
        params=[Param(name="value", type_token="int", ref=ref)],
    )


# ---------------------------------------------------------------------------
# IR model
# ---------------------------------------------------------------------------


class TestIR:
    def test_param_ref_description_roundtrip(self) -> None:
        p = Param(name="start_date", type_token="str", ref="start_date", description="inclusive")
        assert p.ref == "start_date"
        assert p.description == "inclusive"
        restored = Param.model_validate_json(p.model_dump_json())
        assert restored.ref == "start_date"
        assert restored.description == "inclusive"

    def test_param_refs_default_to_none(self) -> None:
        p = Param(name="x", type_token="str")
        assert p.ref is None
        assert p.description is None

    def test_graph_params_roundtrip(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3, description="a param")})
        restored = Graph.model_validate_json(g.model_dump_json())
        assert restored.params["p"].value == 3
        assert restored.params["p"].description == "a param"

    def test_graph_params_key_must_match_param_name(self) -> None:
        with pytest.raises(ValueError, match="Graph.params key"):
            Graph(params={"a": Param(name="b", type_token="str")})

    def test_schema_version_is_two(self) -> None:
        assert CURRENT_SCHEMA_VERSION == 2


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    def test_v1_document_migrates_to_v2_with_empty_params(self) -> None:
        doc = {"schema_version": 1, "paradigm": "functional", "nodes": {}, "edges": {}}
        graph = deserialize_graph(json.dumps(doc))
        assert graph.schema_version == 2
        assert graph.params == {}


# ---------------------------------------------------------------------------
# Resolution / materialization
# ---------------------------------------------------------------------------


class TestResolution:
    def test_resolve_applies_overrides_on_top_of_defaults(self) -> None:
        g = Graph(
            params={"start_date": Param(name="start_date", type_token="str", value="2026-01-01")}
        )
        assert resolve_graph_params(g) == {"start_date": "2026-01-01"}
        assert resolve_graph_params(g, overrides={"start_date": "2026-02-01"}) == {
            "start_date": "2026-02-01"
        }

    def test_resolve_rejects_unknown_override(self) -> None:
        g = Graph(params={"a": Param(name="a", type_token="int", value=1)})
        with pytest.raises(GraphParamError, match="'bogus'"):
            resolve_graph_params(g, overrides={"bogus": 2})

    def test_materialize_bakes_refs_without_mutating_input(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        materialized = materialize_graph(g)
        assert materialized is not g
        assert materialized.nodes["n"].params[0].value == 3
        assert g.nodes["n"].params[0].value is None  # input untouched

    def test_materialize_applies_overrides(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        assert materialize_graph(g, params={"p": 9}).nodes["n"].params[0].value == 9

    def test_materialize_recurses_into_subgraph(self) -> None:
        sub = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        sub.nodes["n"] = _sink_node(ref="p")
        composite = Node(id="c", type="layout.composite", subgraph=sub)
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["c"] = composite
        materialized = materialize_graph(g, params={"p": 7})
        assert materialized.nodes["c"].subgraph.nodes["n"].params[0].value == 7


# ---------------------------------------------------------------------------
# Validation diagnostics
# ---------------------------------------------------------------------------


class TestValidation:
    def test_ref_unresolved_is_error(self) -> None:
        g = Graph(nodes={"n": _sink_node(ref="missing")})
        codes = [d.code for d in validate(g).diagnostics]
        assert "ref_unresolved" in codes
        assert not validate(g).ok

    def test_ref_not_supported_is_error(self) -> None:
        g = Graph(
            params={"p": Param(name="p", type_token="str", value="x")},
            nodes={
                "n": Node(
                    id="n",
                    type=_GraphParamPlain.type,
                    label=_GraphParamPlain.label,
                    ports=[Port(id="n-out", name="out", direction=Direction.OUT, data_type="int")],
                    params=[Param(name="plain", type_token="str", ref="p")],
                )
            },
        )
        codes = [d.code for d in validate(g).diagnostics]
        assert "ref_not_supported" in codes

    def test_ref_type_mismatch_is_error(self) -> None:
        g = Graph(
            params={"p": Param(name="p", type_token="str", value="x")},
            nodes={"n": _sink_node(ref="p")},
        )
        diags = validate(g).diagnostics
        mismatch = next(d for d in diags if d.code == "ref_type_mismatch")
        assert mismatch.expected_type == "int"
        assert mismatch.actual_type == "str"

    def test_valid_ref_has_no_ref_diagnostics(self) -> None:
        g = Graph(
            params={"p": Param(name="p", type_token="int", value=3)},
            nodes={"n": _sink_node(ref="p")},
        )
        assert not [d for d in validate(g).diagnostics if d.code.startswith("ref_")]

    def test_enforce_validation_gate_blocks_unresolved_ref(self) -> None:
        from emergentflow.codegen.validation import enforce_validation_gate

        g = Graph(nodes={"n": _sink_node(ref="missing")})
        with pytest.raises(GraphValidationError, match="ref_unresolved"):
            enforce_validation_gate(g)


# ---------------------------------------------------------------------------
# Codegen
# ---------------------------------------------------------------------------


class TestCodegen:
    def test_main_takes_graph_params_as_keyword_arguments(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        source = compile_to_code(g)
        assert "def main(*, p=" in source
        assert "out0 = p" in source or "= p" in source

    def test_non_parameterized_graph_emits_plain_main(self) -> None:
        g = Graph()
        assert "def main()" in compile_to_code(g)

    def test_assemble_exposes_param_names_and_defaults(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        assembled = _assemble(g)
        assert assembled.graph_param_names == {"p": "p"}
        assert assembled.graph_param_defaults == [("p", "3")]


# ---------------------------------------------------------------------------
# execute(graph, *, params=)
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_uses_default_then_override(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        assert execute(g)["n"] == {"out": 3}
        assert execute(g, params={"p": 10})["n"] == {"out": 10}

    def test_execute_does_not_mutate_graph(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        execute(g, params={"p": 10})
        assert g.nodes["n"].params[0].value is None
        assert g.params["p"].value == 3

    def test_execute_unknown_override_raises(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        g.nodes["n"] = _sink_node(ref="p")
        with pytest.raises(GraphParamError, match="'bogus'"):
            execute(g, params={"bogus": 1})

    def test_execute_unresolved_ref_raises_validation_error_not_key_error(self) -> None:
        g = Graph(nodes={"n": _sink_node(ref="missing")})
        with pytest.raises(GraphValidationError):
            execute(g)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    def test_capture_run_records_params(self) -> None:
        g = Graph(params={"p": Param(name="p", type_token="int", value=3)})
        assert capture_run(g).params == {"p": 3}
        assert capture_run(g, params={"p": 10}).params == {"p": 10}

    def test_capture_run_empty_params_for_plain_graph(self) -> None:
        assert capture_run(Graph()).params == {}


# ---------------------------------------------------------------------------
# CLI --param
# ---------------------------------------------------------------------------


class TestCli:
    @pytest.fixture(autouse=True)
    def _reset_runs_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default RunStore is a process-wide singleton; reset it so each test
        can `configure_runs` its own tmp_path (mirrors how `emergentflow run` works)."""
        import emergentflow.server.runs as runs_mod

        monkeypatch.setattr(runs_mod, "_default_runs", None)
        monkeypatch.setattr(runs_mod, "_configured_runs_root", None)
        monkeypatch.setattr(runs_mod, "_configured_runs_keep", 50)

    def _write_graph(self, tmp_path: pathlib.Path, name: str) -> pathlib.Path:
        path = tmp_path / name
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "paradigm": "functional",
                    "name": "cli-param-test",
                    "params": {"p": {"name": "p", "type_token": "int", "value": 3}},
                    "nodes": {},
                    "edges": {},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_run_with_param_override_records_resolved_params(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from emergentflow.cli import main

        graph_file = self._write_graph(tmp_path, "graph.json")
        monkeypatch.chdir(tmp_path)
        assert main(["run", str(graph_file), "--param", "p=10"]) == 0
        records = list((tmp_path / ".ef-runs").rglob("run.json"))
        assert records, "expected a run record under .ef-runs"
        run_data = json.loads(records[0].read_text(encoding="utf-8"))
        assert run_data["reproducibility"]["params"] == {"p": 10}

    def test_run_unknown_param_is_error(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        from emergentflow.cli import main

        graph_file = self._write_graph(tmp_path, "graph.json")
        monkeypatch.chdir(tmp_path)
        assert main(["run", str(graph_file), "--param", "bogus=1"]) == 1

    def test_run_bad_int_param_is_error(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        from emergentflow.cli import main

        graph_file = self._write_graph(tmp_path, "graph.json")
        monkeypatch.chdir(tmp_path)
        assert main(["run", str(graph_file), "--param", "p=abc"]) == 1
