"""
emergentflow.llm.replay
~~~~~~~~~~~~~~~~~~~~~~~
`ReplayClient` — the pure `LLMClient` implementation (ADR 0017) used by tests
and the ADR-0002 equivalence harness. Replays a recorded `LLMResponse` keyed
by the requesting `LLMRequest.content_hash()`; never touches the network.

Fixtures are content-addressed JSON files, one per recorded response, named
`<content_hash>.json`. `write_fixture` is the companion writer used to seed
fixtures from a live (or hand-built) `LLMResponse`.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from emergentflow.llm.protocol import FixtureMissError, LLMRequest, LLMResponse, Usage


def _fixture_path(fixtures_dir: Path, content_hash: str) -> Path:
    return fixtures_dir / f"{content_hash}.json"


def _response_to_dict(response: LLMResponse) -> dict:
    """Serialize an `LLMResponse` to a JSON-native dict (nested `Usage` flattened)."""
    payload = dataclasses.asdict(response)
    return payload


def _response_from_dict(payload: dict) -> LLMResponse:
    """Reconstruct an `LLMResponse` from the dict shape `_response_to_dict` writes."""
    usage_payload = payload["usage"]
    return LLMResponse(
        text=payload["text"],
        data=payload["data"],
        model=payload["model"],
        usage=Usage(
            input_tokens=usage_payload["input_tokens"],
            output_tokens=usage_payload["output_tokens"],
        ),
        cost_usd=payload["cost_usd"],
        latency_ms=payload["latency_ms"],
        finish_reason=payload["finish_reason"],
    )


def write_fixture(
    fixtures_dir: str | os.PathLike[str], request: LLMRequest, response: LLMResponse
) -> Path:
    """Write *response* as a content-addressed fixture for *request*.

    Creates *fixtures_dir* if it does not already exist. The fixture file is
    named `<request.content_hash()>.json`. Returns the path written.

    This is the seeding path used by tests to record fixtures without
    hand-writing JSON, and by any future `--record` tooling that captures a
    live provider response.
    """
    dir_path = Path(fixtures_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = _fixture_path(dir_path, request.content_hash())
    path.write_text(json.dumps(_response_to_dict(response), indent=2, sort_keys=True) + "\n")
    return path


class ReplayClient:
    """A pure `LLMClient` that replays recorded `LLMResponse`s from disk.

    Structurally satisfies `emergentflow.llm.protocol.LLMClient` (no
    inheritance required — see that module's `Protocol`).

    Parameters
    ----------
    fixtures_dir:
        Directory containing `<content_hash>.json` fixture files. The caller
        (a test, the equivalence harness) is responsible for choosing this
        path; this class has no default so the library stays agnostic of
        where any particular caller keeps its fixtures.
    """

    def __init__(self, fixtures_dir: str | os.PathLike[str]) -> None:
        self.fixtures_dir = Path(fixtures_dir)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Replay the fixture recorded for *request*.

        Raises
        ------
        FixtureMissError
            If no fixture file exists for `request.content_hash()`. The
            message includes the hash and a copy-pasteable
            `write_fixture(...)` call the developer can use to record one.
        """
        content_hash = request.content_hash()
        path = _fixture_path(self.fixtures_dir, content_hash)
        if not path.exists():
            raise FixtureMissError(
                f"No recorded fixture for request hash {content_hash!r} "
                f"(looked in {self.fixtures_dir}). To record one:\n"
                f"    from emergentflow.llm.replay import write_fixture\n"
                f"    write_fixture({str(self.fixtures_dir)!r}, request, response)  "
                f"# response is the LLMResponse you want this request to replay"
            )
        payload = json.loads(path.read_text())
        return _response_from_dict(payload)
