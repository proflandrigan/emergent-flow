"""
emergentflow.llm.gateway
~~~~~~~~~~~~~~~~~~~~~~~~
`GatewayClient` — the effectful `LLMClient` implementation (ADR 0017) that
routes a completion call through LiteLLM, a unified multi-provider gateway
(MIT license; optional `emergentflow[llm]` extra so a bare install stays
light per ADR 0007).

The API key is never read from the IR or from `LLMRequest` as a literal —
only an env-var *name* (`LLMRequest.api_key_env`) or a connection-profile *name*
(`LLMRequest.llm_connection`) is threaded through; `GatewayClient` resolves the actual key
from `os.environ` (and, for a profile reference, from the local connection-profile store
first) at call time (ADR 0017 secrets rule).

`cost_usd` is always returned as `0.0` here on purpose: cost computation is
centralized in `emergentflow.llm.call()` (a pure function of `model` and
`usage`, backed by a price table), not duplicated per client backend.
"""

from __future__ import annotations

import os
import time

from emergentflow.llm.env import MissingAPIKeyError, resolve_effective_api_key_env_name
from emergentflow.llm.protocol import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingUsage,
    LLMRequest,
    LLMResponse,
    Usage,
)


class GatewayResponseError(RuntimeError):
    """Raised when LiteLLM's response cannot be turned into an `LLMResponse`.

    E.g. `response_format == "json"` was requested but the provider's
    content was not valid JSON.
    """


class GatewayClient:
    """An effectful `LLMClient` that routes calls through LiteLLM.

    Structurally satisfies `emergentflow.llm.protocol.LLMClient` (no
    inheritance required — see that module's `Protocol`).
    """

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send *request* to the provider via LiteLLM and return an `LLMResponse`.

        Raises
        ------
        ModuleNotFoundError
            Re-raised with an install hint if `litellm` is not installed.
        MissingAPIKeyError
            If the resolved env var is unset.
        GatewayResponseError
            If `response_format == "json"` and the provider's content is not
            valid JSON.
        """
        try:
            import litellm
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "emergentflow.llm.gateway.GatewayClient needs the `llm` extra "
                f"(missing dependency: {exc.name}).\n"
                "Install it with:  pip install 'emergentflow[llm]'"
            ) from exc

        env_name = resolve_effective_api_key_env_name(
            request.provider, request.api_key_env, request.llm_connection
        )
        api_key = os.environ.get(env_name)
        if not api_key:
            raise MissingAPIKeyError(
                f"Environment variable {env_name!r} is not set. "
                f"Export it before running a graph with an LLM node, e.g.:\n"
                f"    export {env_name}=<your api key>"
            )

        kwargs: dict = {
            "model": f"{request.provider}/{request.model}",
            "messages": [dict(m) for m in request.messages],
            "temperature": request.temperature,
            "api_key": api_key,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        start = time.perf_counter()
        response = litellm.completion(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000.0

        choice = response.choices[0]
        content = choice.message.content
        finish_reason = choice.finish_reason or "stop"
        response_usage = getattr(response, "usage", None)
        if response_usage is None:
            raise GatewayResponseError(
                "Provider response did not include token usage; "
                "cannot compute cost/tokens for this call."
            )
        usage = Usage(
            input_tokens=response_usage.prompt_tokens,
            output_tokens=response_usage.completion_tokens,
        )
        # `request.model` (bare, unprefixed) is what `PRICE_TABLE_PER_1K_TOKENS`
        # (emergentflow.llm.pricing) is keyed by. LiteLLM's `response.model` can
        # come back prefixed with the provider (the same `f"{provider}/{model}"`
        # string sent as the request's `model` kwarg above), which would silently
        # miss the price table and report `cost_usd=0.0` for a real, billed call.
        # Always report the bare model id `call()` was asked for.
        model = request.model

        text: str | None = content
        data: dict | None = None
        if request.response_format == "json":
            import json

            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise GatewayResponseError(
                    f"Requested response_format='json' but the provider's content "
                    f"was not valid JSON: {exc}"
                ) from exc
            text = None

        return LLMResponse(
            text=text,
            data=data,
            model=model,
            usage=usage,
            cost_usd=0.0,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Send *request* to the provider's embedding endpoint via LiteLLM.

        Raises
        ------
        ModuleNotFoundError
            Re-raised with an install hint if ``litellm`` is not installed.
        MissingAPIKeyError
            If the resolved env var is unset.
        """
        try:
            import litellm
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "emergentflow.llm.gateway.GatewayClient needs the `llm` extra "
                f"(missing dependency: {exc.name}).\n"
                "Install it with:  pip install 'emergentflow[llm]'"
            ) from exc

        env_name = resolve_effective_api_key_env_name(
            request.provider, request.api_key_env, request.llm_connection
        )
        api_key = os.environ.get(env_name)
        if not api_key:
            raise MissingAPIKeyError(
                f"Environment variable {env_name!r} is not set. "
                f"Export it before running a graph with an embedding node, e.g.:\n"
                f"    export {env_name}=<your api key>"
            )

        start = time.perf_counter()
        response = litellm.embedding(
            model=f"{request.provider}/{request.model}",
            input=list(request.texts),
            api_key=api_key,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        response_usage = getattr(response, "usage", None)
        input_tokens = response_usage.prompt_tokens if response_usage else 0

        vectors: list[list[float]] = [item["embedding"] for item in response.data]
        dimensions = len(vectors[0]) if vectors else 0

        return EmbeddingResponse(
            embeddings=vectors,
            model=request.model,
            dimensions=dimensions,
            usage=EmbeddingUsage(input_tokens=input_tokens),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )
