"""
tests/test_llm_prompt.py
~~~~~~~~~~~~~~~~~~~~~~~~
Golden + ADR-0002 equivalence tests for the `llm.prompt` node, its
variable-substitution validation, optional wired template override,
and the `prompt -> call` composition (Epic 9 Story 3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import emergentflow as ef
from emergentflow.ir import Direction, Edge, Graph, Node, Param, Port, PortRef
from emergentflow.llm import call
from emergentflow.llm.protocol import LLMResponse, Usage
from emergentflow.llm.templating import PromptVariableError
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.examples.llm_prompt import LlmPrompt
from emergentflow.nodes.examples.llm_prompt_from_file import LlmPromptFromFile
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import ParamSpec, PortSpec


@register
class _TestVarsSource(NodeDefinition):
    """Test fixture: 0 in, 1 out, produces a VariableBinding (dict) for tests."""

    type = "test.vars_source"
    family = "test"
    label = "VarsSrc"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="VariableBinding")]
    params = [ParamSpec(name="value", type_token="dict", default={})]

    def codegen(self, node: Node, ctx) -> CodeFragment:
        val = next(p.value for p in node.params if p.name == "value")
        return CodeFragment(body=f"{ctx.out_var('out')} = {val!r}")

    def execute(self, node: Node, inputs: dict) -> dict:
        val = next(p.value for p in node.params if p.name == "value")
        return {"out": val}


def test_llm_prompt_golden_preview_code():
    """The node's codegen preview is deterministic, readable ef.llm.prompt(...) source."""
    node = LlmPrompt().instantiate(system="You are {{persona}}.", user="{{question}}")
    frag = LlmPrompt().preview(node)

    assert "ef.llm.prompt(" in frag.body
    assert "You are {{persona}}." in frag.body
    assert "{{question}}" in frag.body
    # Deterministic: previewing twice yields byte-identical source.
    assert LlmPrompt().preview(node).body == frag.body


def test_llm_prompt_node_equivalence():
    """execute() and the codegen preview (exec'd) produce an identical PromptSpec."""
    node = LlmPrompt().instantiate(system="You are {{persona}}.", user="{{question}}")
    variables = {"persona": "helpful", "question": "What is 2+2?"}

    # codegen side: preview() builds a trivial port-name-identity context, so
    # the emitted body references a free variable named "variables" -- seed
    # the exec scope with it under that name (mirrors the established
    # tests/test_reference_nodes.py::_run_codegen pattern).
    # The new optional ports also get variable names equal to their port names;
    # seed them as None so the ternary fallback picks the literal param.
    frag = LlmPrompt().preview(node)
    scope = {"variables": variables, "system_template": None, "user_template": None}
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    codegen_result = scope["prompt"]

    exec_result = LlmPrompt().execute(node, {"variables": variables})["prompt"]

    assert codegen_result == exec_result
    assert codegen_result.system == "You are helpful."
    assert codegen_result.user == "What is 2+2?"
    assert codegen_result.messages == (
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "What is 2+2?"},
    )


def test_llm_prompt_missing_variable_raises():
    """A template referencing a variable absent from the binding raises PromptVariableError."""
    node = LlmPrompt().instantiate(system="Hi {{name}}", user="go")
    with pytest.raises(PromptVariableError, match="name"):
        LlmPrompt().execute(node, {"variables": {}})


def test_llm_prompt_extra_variable_raises():
    """A binding supplying a variable no template references raises PromptVariableError."""
    node = LlmPrompt().instantiate(system="Hi", user="go")
    with pytest.raises(PromptVariableError, match="unused"):
        LlmPrompt().execute(node, {"variables": {"unused": "x"}})


def test_llm_prompt_to_llm_call_wiring():
    """PromptSpec.messages, produced by llm.prompt, feeds directly into llm.call's messages."""
    node = LlmPrompt().instantiate(
        system="You are a {{persona}} assistant.", user="Answer: {{question}}"
    )
    prompt_spec = LlmPrompt().execute(
        node, {"variables": {"persona": "helpful", "question": "2+2?"}}
    )["prompt"]

    class FakeClient:
        def complete(self, request):
            assert request.messages == prompt_spec.messages
            return LLMResponse(
                text="4",
                data=None,
                model=request.model,
                usage=Usage(input_tokens=1, output_tokens=1),
                cost_usd=0.0,
                latency_ms=1.0,
                finish_reason="stop",
            )

    response = call(
        prompt_spec.messages, provider="anthropic", model="claude-sonnet-5", client=FakeClient()
    )
    assert response.text == "4"


def test_unwired_ports_use_literal_params():
    """Optional ports left unconnected (None inputs) fall back to literal params."""
    node = LlmPrompt().instantiate(system="literal system", user="literal user")

    # Both overrides explicitly passed as None
    result_explicit = LlmPrompt().execute(
        node, {"variables": {}, "system_template": None, "user_template": None}
    )["prompt"]

    # Both overrides omitted from inputs
    result_omitted = LlmPrompt().execute(node, {"variables": {}})["prompt"]

    # Both should match the original behavior (no overrides)
    result_baseline = LlmPrompt().execute(node, {"variables": {}})["prompt"]
    assert result_explicit == result_baseline
    assert result_omitted == result_baseline
    assert result_explicit.system == "literal system"
    assert result_explicit.user == "literal user"


def test_system_template_override():
    """Wired system_template overrides the literal system param at execute time."""
    node = LlmPrompt().instantiate(system="literal system", user="literal user")
    result = LlmPrompt().execute(
        node, {"variables": {}, "system_template": "override system", "user_template": None}
    )["prompt"]
    assert result.system == "override system"
    assert result.user == "literal user"


def test_user_template_override():
    """Wired user_template overrides the literal user param at execute time."""
    node = LlmPrompt().instantiate(system="literal system", user="literal user")
    result = LlmPrompt().execute(
        node, {"variables": {}, "system_template": None, "user_template": "override user"}
    )["prompt"]
    assert result.system == "literal system"
    assert result.user == "override user"


def test_both_template_overrides():
    """Both wired overrides override their respective literal params."""
    node = LlmPrompt().instantiate(system="literal system", user="literal user")
    result = LlmPrompt().execute(
        node,
        {"variables": {}, "system_template": "sys override", "user_template": "usr override"},
    )["prompt"]
    assert result.system == "sys override"
    assert result.user == "usr override"


def test_codegen_emits_fallback_ternary():
    """Codegen preview emits two `is not None else` clauses (one per optional port)."""
    node = LlmPrompt().instantiate(system="sys", user="usr")
    frag = LlmPrompt().preview(node)
    assert frag.body.count("is not None else") == 2


def test_adr_0002_equivalence_wired_from_file(tmp_path: Path) -> None:
    """compile_to_code(ir) == execute(ir) when llm.prompt_from_file wires into llm.prompt."""
    filepath = tmp_path / "prompt.md"
    filepath.write_text("You are {{persona}} assistant.")

    file_node = LlmPromptFromFile().instantiate(path=str(filepath))
    prompt_node = LlmPrompt().instantiate(system="", user="Answer {{question}}")
    vars_node = Node(
        id="vars",
        type=_TestVarsSource.type,
        label=_TestVarsSource.label,
        ports=[
            Port(id="vars-out", name="out", direction=Direction.OUT, data_type="VariableBinding"),
        ],
        params=[
            Param(
                name="value",
                type_token="dict",
                value={"persona": "helpful", "question": "what is 2+2?"},
            ),
        ],
    )

    file_out = next(p for p in file_node.ports if p.direction == Direction.OUT)
    prompt_sys_in = next(p for p in prompt_node.ports if p.name == "system_template")
    prompt_vars_in = next(p for p in prompt_node.ports if p.name == "variables")
    vars_out = next(p for p in vars_node.ports if p.direction == Direction.OUT)

    edges = [
        Edge(
            source=PortRef(node_id=file_node.id, port_id=file_out.id),
            target=PortRef(node_id=prompt_node.id, port_id=prompt_sys_in.id),
        ),
        Edge(
            source=PortRef(node_id=vars_node.id, port_id=vars_out.id),
            target=PortRef(node_id=prompt_node.id, port_id=prompt_vars_in.id),
        ),
    ]
    graph = Graph(
        nodes={file_node.id: file_node, prompt_node.id: prompt_node, vars_node.id: vars_node},
        edges={e.id: e for e in edges},
    )

    exec_results = ef.execute(graph)
    exec_prompt = exec_results[prompt_node.id]["prompt"]

    source = ef.compile_to_code(graph)
    scope: dict = {}
    exec(source, scope)  # noqa: S102 -- test-only, trusted source
    compiled_results = scope["main"]()
    # The leaf OUT port (prompt) is the only result; key is a variable name, not node ID.
    compiled_prompt = next(iter(compiled_results.values()))

    assert exec_prompt == compiled_prompt
    assert exec_prompt.system == "You are helpful assistant."
    assert exec_prompt.user == "Answer what is 2+2?"
