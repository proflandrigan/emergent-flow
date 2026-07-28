"""
tests/test_llm_gateway.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Regression tests for `emergentflow.llm.gateway.GatewayClient`'s response parsing.

`GatewayClient` had no direct unit tests exercising `complete()`'s parsing of an actual
LiteLLM response shape -- every other reference to it in the test suite only checked
whether it was constructed. Gated by `pytest.importorskip("litellm")` per the project's
optional-`[llm]`-extra test convention (mirrors the torch-gated declarative tests); these
tests never make a network call, they monkeypatch `litellm.completion` to return a real
`litellm.types.utils.ModelResponse` built in-process.
"""

from __future__ import annotations

import pytest

litellm = pytest.importorskip("litellm")

from litellm.types.utils import Choices, Message, ModelResponse  # noqa: E402
from litellm.types.utils import Usage as LiteLLMUsage  # noqa: E402

from emergentflow.llm.gateway import GatewayClient, GatewayResponseError  # noqa: E402
from emergentflow.llm.protocol import LLMRequest  # noqa: E402


def _model_response(*, content: str | None, finish_reason: str = "stop") -> ModelResponse:
    return ModelResponse(
        choices=[
            Choices(
                finish_reason=finish_reason,
                index=0,
                message=Message(content=content, role="assistant"),
            )
        ],
        usage=LiteLLMUsage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
        model="anthropic/claude-sonnet-5",
    )


def test_complete_json_mode_none_content_raises_gateway_response_error(monkeypatch):
    """A tool-call/refusal completion (content=None) in JSON mode raises GatewayResponseError,
    not a raw TypeError from `json.loads(None)`."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kwargs: _model_response(content=None, finish_reason="tool_calls"),
    )

    request = LLMRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        messages=({"role": "user", "content": "give me json"},),
        response_format="json",
    )

    with pytest.raises(GatewayResponseError, match="no message content"):
        GatewayClient().complete(request)


def test_complete_json_mode_malformed_content_raises_gateway_response_error(monkeypatch):
    """Non-JSON (but non-None) content in JSON mode still raises GatewayResponseError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _model_response(content="not json"))

    request = LLMRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        messages=({"role": "user", "content": "give me json"},),
        response_format="json",
    )

    with pytest.raises(GatewayResponseError, match="was not valid JSON"):
        GatewayClient().complete(request)


def test_complete_json_mode_valid_content_parses(monkeypatch):
    """Sanity check: well-formed JSON content still parses correctly (no regression)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        litellm, "completion", lambda **kwargs: _model_response(content='{"answer": 42}')
    )

    request = LLMRequest(
        provider="anthropic",
        model="claude-sonnet-5",
        messages=({"role": "user", "content": "give me json"},),
        response_format="json",
    )

    response = GatewayClient().complete(request)
    assert response.data == {"answer": 42}
    assert response.text is None
