"""
emergentflow.llm.protocol
~~~~~~~~~~~~~~~~~~~~~~~~~
The `LLMClient` seam (ADR 0017): the single injected boundary between the
pure SDK core and any real or replayed LLM provider call.

`LLMRequest` is a pure, JSON-native, hashable description of one completion
call — building it from node inputs is pure. `LLMResponse` is the inspectable
result carried on every `ef.llm.call` node's OUT port (satisfies
`emergentflow.api.is_inspectable`; a live provider SDK object is never
returned). `LLMClient` is a `Protocol` with one method, `complete`, so any
object with that method (a `ReplayClient`, a `GatewayClient`, a test double)
satisfies it without inheritance.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any, Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class LLMRequest:
    """A pure, JSON-native description of one LLM completion call.

    Attributes
    ----------
    provider: gateway provider key, e.g. ``"anthropic"``.
    model: provider model id, e.g. ``"claude-sonnet-5"``.
    messages: ``[{"role": "system" | "user" | "assistant", "content": str}, ...]``.
    temperature: sampling temperature; defaults to ``0`` for reproducibility.
    max_tokens: optional output token cap.
    response_format: ``"text"`` or ``"json"``.
    response_schema: optional JSON Schema the response must validate against
        when ``response_format == "json"``.
    api_key_env: name of the environment variable holding the provider API
        key (never the key itself — ADR 0017 secrets rule). ``None`` lets the
        client fall back to a provider-conventional env-var name.
    llm_connection: name of a registered LLM credential profile
        (``emergentflow.connections.profiles.LlmConnectionProfile``) whose ``api_key_env`` field
        should be used instead. Resolved to a real env-var name only inside
        `GatewayClient.complete()` / the pre-flight check — never here, and never in
        `compile_to_code`/`execute` (ADR 0002 purity: resolving a profile NAME requires reading
        connections.toml, which is I/O). ``None`` means no profile reference; fall back to
        `api_key_env` / the provider-conventional default.
    """

    provider: str
    model: str
    messages: tuple[dict[str, str], ...]
    temperature: float = 0.0
    max_tokens: int | None = None
    response_format: str = "text"
    response_schema: dict[str, Any] | None = None
    api_key_env: str | None = None
    llm_connection: str | None = None

    def content_hash(self) -> str:
        """Return a stable sha256 hex digest identifying this request's content.

        Used by `ReplayClient` to key recorded fixtures. Built from a
        JSON-native, sorted-keys serialization of every field so the hash is
        stable across process runs and Python versions.
        """
        payload = {
            "provider": self.provider,
            "model": self.model,
            "messages": [dict(m) for m in self.messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": self.response_format,
            "response_schema": self.response_schema,
            # api_key_env / llm_connection are deliberately excluded: they name an env var or a
            # connection profile, not a secret, but neither has any bearing on what response a
            # given request content should replay -- two requests that are otherwise identical
            # should hit the same fixture regardless of which credential reference was configured.
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class Usage:
    """Token counts for one completion call."""

    input_tokens: int
    output_tokens: int


@dataclasses.dataclass(frozen=True)
class LLMResponse:
    """The inspectable result of one LLM completion call (ADR 0017, Epic 9 Story 2).

    JSON-native so it satisfies `emergentflow.api.is_inspectable`; a live
    provider SDK response object must never be returned from a node.

    Attributes
    ----------
    text: the raw completion text, or ``None`` when ``response_format`` was
        ``"json"`` and parsing succeeded (see `data`).
    data: the parsed + schema-validated structured output, or ``None`` when
        ``response_format`` was ``"text"``.
    model: the model id that actually served the request.
    usage: input/output token counts.
    cost_usd: computed cost for this call (pure function of `model` and
        `usage`; see `emergentflow.llm.pricing`).
    latency_ms: wall-clock latency reported by the client.
    finish_reason: provider-reported stop reason, e.g. ``"stop"``.
    """

    text: str | None
    data: dict[str, Any] | None
    model: str
    usage: Usage
    cost_usd: float
    latency_ms: float
    finish_reason: str


class FixtureMissError(LookupError):
    """Raised by `ReplayClient` when a request's content hash has no recorded fixture.

    The message includes the request's `content_hash()` and a
    copy-pasteable hint for how to re-record fixtures, so a developer hitting
    this in a test run knows exactly what to do next.
    """


@runtime_checkable
class LLMClient(Protocol):
    """The injected-client seam every LLM-call node depends on (ADR 0017).

    Any object exposing a `complete(request: LLMRequest) -> LLMResponse`
    method satisfies this protocol structurally (no inheritance required) --
    `ReplayClient` and `GatewayClient` are the two implementations that ship
    with this package.
    """

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one completion call and return an inspectable `LLMResponse`."""
        ...
