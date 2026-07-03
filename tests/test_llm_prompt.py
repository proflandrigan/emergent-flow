"""
tests/test_llm_prompt.py
~~~~~~~~~~~~~~~~~~~~~~~~
Golden + ADR-0002 equivalence tests for the `llm.prompt` node, its
variable-substitution validation, and the `prompt -> call` composition
(Epic 9 Story 3).
"""

from __future__ import annotations

import pytest

from emergentflow.llm import call
from emergentflow.llm.protocol import LLMResponse, Usage
from emergentflow.llm.templating import PromptVariableError
from emergentflow.nodes.examples.llm_prompt import LlmPrompt


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
    frag = LlmPrompt().preview(node)
    scope = {"variables": variables}
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
