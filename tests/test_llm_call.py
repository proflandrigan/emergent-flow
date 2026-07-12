"""
tests/test_llm_call.py
~~~~~~~~~~~~~~~~~~~~~~
Golden + ADR-0002 equivalence tests for the `llm.call` node (Epic 9 Story 2).
"""

from __future__ import annotations

import dataclasses

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.ir import Graph, Paradigm, serialize_graph
from emergentflow.llm.protocol import LLMRequest, LLMResponse, Usage
from emergentflow.llm.replay import ReplayClient, write_fixture
from emergentflow.nodes.examples.llm_call import LlmCall


def _single_node_graph(**overrides):
    node = LlmCall().instantiate(**overrides)
    graph = Graph(
        name="llm_call_test", paradigm=Paradigm.FUNCTIONAL, nodes={node.id: node}, edges={}
    )
    return graph, node


def test_llm_call_golden_emitted_code():
    """compile_to_code emits a deterministic ef.llm.call(...) with threaded client."""
    graph, _node = _single_node_graph(
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        model="claude-sonnet-5",
        temperature=0.0,
    )
    code = compile_to_code(graph)

    assert "def main(*, client: object | None = None) -> dict[str, object]:" in code
    assert "ef.llm.call(" in code
    assert 'provider="anthropic"' in code
    assert 'model="claude-sonnet-5"' in code
    assert "client=client" in code
    # compile_to_code is a pure function of the graph: recompiling must be
    # byte-identical.
    assert compile_to_code(graph) == code


def test_llm_call_equivalence_text(tmp_path):
    """execute() and the compiled module produce an identical LLMResponse for text output."""
    graph, node = _single_node_graph(
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        model="claude-sonnet-5",
    )
    request = LLMRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        messages=({"role": "user", "content": "hi"},),
        temperature=0.0,
        max_tokens=None,
        response_format="text",
        response_schema=None,
        api_key_env=None,
    )
    response = LLMResponse(
        text="hello from fixture",
        data=None,
        model="claude-sonnet-5",
        usage=Usage(input_tokens=10, output_tokens=4),
        cost_usd=0.0,
        latency_ms=42.0,
        finish_reason="stop",
    )
    write_fixture(tmp_path, request, response)
    client = ReplayClient(tmp_path)

    exec_results = execute(graph, client=client)
    exec_response = exec_results[node.id]["response"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(compile(code, "<compiled>", "exec"), ns)
    compiled_results = ns["main"](client=client)
    compiled_response = next(iter(compiled_results.values()))

    assert dataclasses.astuple(exec_response) == dataclasses.astuple(compiled_response)
    assert exec_response.text == "hello from fixture"
    # cost_usd is recomputed by ef.llm.call() from the price table, not the
    # fixture's 0.0 placeholder -- proves the cost-centralization design.
    assert exec_response.cost_usd > 0.0


def test_llm_call_equivalence_json_with_schema(tmp_path):
    """execute() and the compiled module agree for structured (json) output, schema-validated."""
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    graph, node = _single_node_graph(
        messages=[{"role": "user", "content": "give me json"}],
        provider="anthropic",
        model="claude-sonnet-5",
        response_format="json",
        response_schema=schema,
    )
    request = LLMRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        messages=({"role": "user", "content": "give me json"},),
        temperature=0.0,
        max_tokens=None,
        response_format="json",
        response_schema=schema,
        api_key_env=None,
    )
    response = LLMResponse(
        text=None,
        data={"answer": 42},
        model="claude-sonnet-5",
        usage=Usage(input_tokens=12, output_tokens=6),
        cost_usd=0.0,
        latency_ms=55.0,
        finish_reason="stop",
    )
    write_fixture(tmp_path, request, response)
    client = ReplayClient(tmp_path)

    exec_results = execute(graph, client=client)
    exec_response = exec_results[node.id]["response"]

    code = compile_to_code(graph)
    ns: dict = {}
    exec(compile(code, "<compiled>", "exec"), ns)
    compiled_results = ns["main"](client=client)
    compiled_response = next(iter(compiled_results.values()))

    assert dataclasses.astuple(exec_response) == dataclasses.astuple(compiled_response)
    assert exec_response.data == {"answer": 42}


def test_llm_call_no_secret_or_env_name_in_ir_or_code(monkeypatch):
    """Neither a secret VALUE nor even the raw env-var NAME appears in IR/code -- only an opaque
    LLM connection profile name does. This is a stronger isolation property than the old
    api_key_env design: resolving a profile name to a real env var now happens only inside the
    effectful GatewayClient, never in the pure IR/codegen path."""
    secret_value = "sk-super-secret-value-should-never-appear-1234567890"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)

    graph, _node = _single_node_graph(
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        model="claude-sonnet-5",
        llm_connection="my_anthropic_profile",
    )

    ir_json = serialize_graph(graph)
    code = compile_to_code(graph)

    assert secret_value not in ir_json
    assert secret_value not in code
    assert "ANTHROPIC_API_KEY" not in ir_json
    assert "ANTHROPIC_API_KEY" not in code
    # The connection profile NAME is expected to appear -- that's the point of the profile-based
    # design: the IR/code carry an opaque reference, never even the env-var name.
    assert "my_anthropic_profile" in ir_json
    assert "my_anthropic_profile" in code
