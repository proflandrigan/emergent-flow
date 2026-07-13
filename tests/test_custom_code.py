"""
tests/test_custom_code.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Golden + ADR-0002 equivalence tests for the `script.custom_code` node.
"""

from __future__ import annotations

from emergentflow.codegen.context import CodegenContext
from emergentflow.nodes.examples.custom_code import CustomCode
from emergentflow.script import CustomCodeError


def test_custom_code_golden_preview_code():
    """The node's codegen preview is deterministic, with a per-node wrapper."""
    node = CustomCode().instantiate(code="def transform(value):\n    return value + 1")
    frag = CustomCode().preview(node)

    assert "def _run_result(value):" in frag.body
    assert "return value + 1" in frag.body
    assert "return transform(value)" in frag.body
    # Deterministic: previewing twice yields byte-identical source.
    assert CustomCode().preview(node).body == frag.body


def test_custom_code_node_equivalence():
    """execute() and the codegen preview (exec'd) produce an identical result."""
    node = CustomCode().instantiate(code="def transform(value):\n    return value + 1")

    frag = CustomCode().preview(node)
    scope = {"value": 41}
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    codegen_result = scope["result"]

    exec_result = CustomCode().execute(node, {"value": 41})["result"]

    assert codegen_result == exec_result == 42


def test_custom_code_dataframe_transform_equivalence():
    """Equivalence holds for dict-based data transforms (ML/stats-like)."""
    node = CustomCode().instantiate(
        code="def transform(value):\n    return {**value, 'derived': value['x'] * 2}"
    )

    frag = CustomCode().preview(node)
    scope = {"value": {"x": 5}}
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    codegen_result = scope["result"]

    exec_result = CustomCode().execute(node, {"value": {"x": 5}})["result"]

    assert codegen_result == exec_result == {"x": 5, "derived": 10}


def test_custom_code_missing_transform_validation():
    """A code param that defines no transform function fails validation."""
    node = CustomCode().instantiate(code="x = 1")
    errors = CustomCode().validate_node(node)
    assert len(errors) > 0
    assert any("transform" in e for e in errors)


def test_custom_code_syntax_error_validation():
    """A code param with a syntax error fails validation."""
    node = CustomCode().instantiate(code="def transform(value)\n    return value")
    errors = CustomCode().validate_node(node)
    assert len(errors) > 0


def test_custom_code_valid_code_passes_validation():
    """Valid transform code passes validation without errors."""
    node = CustomCode().instantiate(code="def transform(value):\n    return value")
    assert CustomCode().validate_node(node) == []


def test_custom_code_execute_missing_transform_raises():
    """Executing code without a transform function raises CustomCodeError."""
    node = CustomCode().instantiate(code="x = 1")
    import pytest

    with pytest.raises(CustomCodeError):
        CustomCode().execute(node, {"value": None})


def test_custom_code_two_nodes_no_collision():
    """Two custom-code nodes with different CodegenContexts produce distinct wrappers."""
    code = "def transform(value):\n    return value"

    node_a = CustomCode().instantiate(code=code, label="a")
    node_b = CustomCode().instantiate(code=code, label="b")

    ctx_a = CodegenContext(in_vars={"value": "v1"}, out_vars={"result": "result_1"})
    ctx_b = CodegenContext(in_vars={"value": "v2"}, out_vars={"result": "result_2"})

    frag_a = CustomCode().codegen(node_a, ctx_a)
    frag_b = CustomCode().codegen(node_b, ctx_b)

    assert "_run_result_1" in frag_a.body
    assert "_run_result_2" in frag_b.body
    assert frag_a.body != frag_b.body
