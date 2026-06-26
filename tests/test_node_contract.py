"""Tests for emergentflow.nodes.contract — NodeDefinition ABC and its helpers."""

import pytest

from emergentflow.ir.common import Direction, Paradigm
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node, Position
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.spec import NodeSpec, ParamSpec, PortSpec, ValidationHints


# A tiny self-contained definition exercising every contract feature.
class _Demo(NodeDefinition):
    type = "demo.thing"
    version = 3
    family = "demo"
    label = "Demo Thing"
    ports = [
        PortSpec(name="in1", direction=Direction.IN, data_type="Table"),
        PortSpec(name="out1", direction=Direction.OUT, data_type="Frame"),
    ]
    params = [
        ParamSpec(
            name="mode",
            type_token="str",
            default="a",
            required=True,
            hints=ValidationHints(choices=["a", "b"]),
        ),
        ParamSpec(name="k", type_token="int", default=1, hints=ValidationHints(min=0, max=10)),
        ParamSpec(
            name="name",
            type_token="str",
            default=None,
            hints=ValidationHints(min_length=2, pattern=r"[a-z]+"),
        ),
    ]

    def codegen(self, node, ctx):
        return CodeFragment(
            imports=["import os"],
            body=f"{ctx.out_var('out1')} = {ctx.in_var('in1')}",
        )

    def execute(self, node, inputs):
        return {"out1": inputs["in1"]}


class TestCodeFragment:
    def test_render_combines_imports_and_body(self):
        frag = CodeFragment(imports=["import os", "import sys"], body="x = 1")
        assert frag.render() == "import os\nimport sys\n\nx = 1"

    def test_render_imports_only(self):
        assert CodeFragment(imports=["import os"]).render() == "import os"

    def test_render_body_only(self):
        assert CodeFragment(body="x = 1").render() == "x = 1"

    def test_round_trip(self):
        frag = CodeFragment(imports=["import os"], body="x = 1")
        assert CodeFragment.model_validate_json(frag.model_dump_json()) == frag


class TestToSpec:
    def test_to_spec_reflects_class_metadata(self):
        spec = _Demo().to_spec()
        assert isinstance(spec, NodeSpec)
        assert spec.type == "demo.thing"
        assert spec.version == 3
        assert spec.family == "demo"
        assert spec.label == "Demo Thing"
        assert spec.paradigm == Paradigm.FUNCTIONAL
        assert [p.name for p in spec.ports] == ["in1", "out1"]
        assert [p.name for p in spec.params] == ["mode", "k", "name"]

    def test_to_spec_is_json_serializable(self):
        spec = _Demo().to_spec()
        assert NodeSpec.model_validate_json(spec.model_dump_json()) == spec


class TestInstantiate:
    def test_builds_valid_ir_node(self):
        node = _Demo().instantiate()
        assert isinstance(node, Node)
        assert node.type == "demo.thing"
        assert node.label == "Demo Thing"
        assert [p.name for p in node.ports] == ["in1", "out1"]
        # defaults flow into both value and default
        values = {p.name: p.value for p in node.params}
        assert values == {"mode": "a", "k": 1, "name": None}

    def test_ports_get_fresh_unique_ids(self):
        node = _Demo().instantiate()
        ids = [p.id for p in node.ports]
        assert len(set(ids)) == len(ids)
        assert all(pid for pid in ids)

    def test_two_instances_have_distinct_node_ids(self):
        assert _Demo().instantiate().id != _Demo().instantiate().id

    def test_param_override_applied(self):
        node = _Demo().instantiate(mode="b", k=5)
        values = {p.name: p.value for p in node.params}
        assert values["mode"] == "b"
        assert values["k"] == 5

    def test_label_and_position_override(self):
        node = _Demo().instantiate(label="Custom", position=Position(x=1.0, y=2.0))
        assert node.label == "Custom"
        assert node.position.x == 1.0

    def test_unknown_override_raises(self):
        with pytest.raises(ValueError, match="unknown param override"):
            _Demo().instantiate(nope=1)

    def test_instantiated_node_fits_in_a_graph(self):
        node = _Demo().instantiate()
        graph = Graph(nodes={node.id: node})
        assert node.id in graph.nodes


class TestValidateNode:
    def test_valid_node_has_no_errors(self):
        node = _Demo().instantiate(mode="a", k=5, name="abc")
        assert _Demo().validate_node(node) == []

    def test_type_mismatch_flagged(self):
        node = Node(type="other.thing")
        errors = _Demo().validate_node(node)
        assert any("does not match definition type" in e for e in errors)

    def test_required_missing_flagged(self):
        node = _Demo().instantiate(mode=None)
        errors = _Demo().validate_node(node)
        assert any("required param 'mode'" in e for e in errors)

    def test_bad_choice_flagged(self):
        node = _Demo().instantiate(mode="z")
        errors = _Demo().validate_node(node)
        assert any("not one of" in e for e in errors)

    def test_numeric_out_of_range_flagged(self):
        node = _Demo().instantiate(k=99)
        errors = _Demo().validate_node(node)
        assert any("above max" in e for e in errors)

    def test_min_length_flagged(self):
        node = _Demo().instantiate(name="a")
        errors = _Demo().validate_node(node)
        assert any("below min_length" in e for e in errors)

    def test_pattern_flagged(self):
        node = _Demo().instantiate(name="ABC")
        errors = _Demo().validate_node(node)
        assert any("does not match pattern" in e for e in errors)

    def test_undeclared_param_flagged(self):
        from emergentflow.ir.params import Param

        node = _Demo().instantiate()
        node.params.append(Param(name="ghost", type_token="str", value="x"))
        errors = _Demo().validate_node(node)
        assert any("is not declared" in e for e in errors)


class TestInferTypes:
    def test_default_returns_out_port_types(self):
        out = _Demo().infer_types(_Demo().instantiate(), {"in1": "Table"})
        assert out == {"out1": "Frame"}


class TestPreview:
    def test_preview_uses_port_names_as_variables(self):
        node = _Demo().instantiate()
        frag = _Demo().preview(node)
        assert frag.body == "out1 = in1"
        assert frag.imports == ["import os"]

    def test_preview_render_round_trips(self):
        node = _Demo().instantiate()
        assert _Demo().preview(node).render() == "import os\n\nout1 = in1"


class TestAbstractEnforcement:
    def test_cannot_instantiate_incomplete_definition(self):
        class Bad(NodeDefinition):
            type = "bad.x"
            family = "bad"
            label = "Bad"

        with pytest.raises(TypeError):
            Bad()  # missing codegen/execute
