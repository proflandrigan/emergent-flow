"""Regression tests for the collaboration payload-digest layer (Epic 17).

Covers the two defects found in the 2026-08-14 follow-up bug hunt:

- ``digest_payload`` JSON truncation must keep ``value`` a stable JSON-object type
  (a dict) and never emit an invalid-JSON byte prefix.
- ``digest_results`` must enforce its 50KB hard cap even against a single oversized
  scalar/text payload.
"""

import json

from emergentflow.collab.digest import (
    MAX_DIGEST_BYTES,
    MAX_JSON_CHARS,
    digest_payload,
    digest_results,
)


def test_json_truncation_keeps_value_as_json_object() -> None:
    payload = {"kind": "json", "value": {"k": "x" * 1200}}
    digested = digest_payload(payload)
    assert isinstance(digested["value"], dict)
    assert digested.get("truncated") is True
    assert digested["original_bytes"] == len(json.dumps(payload["value"], separators=(",", ":")))
    # The value must actually be bounded, not carried through in full behind a
    # truncated flag (digest_payload's JSON contract: payloads over MAX_JSON_CHARS
    # get truncated).
    assert len(json.dumps(digested["value"], separators=(",", ":"))) <= MAX_JSON_CHARS


def test_json_truncation_bounds_value_not_just_flags_it() -> None:
    huge = {"deep": {"nested": "x" * (MAX_JSON_CHARS * 10)}}
    digested = digest_payload({"kind": "json", "value": huge})
    assert digested.get("truncated") is True
    assert isinstance(digested["value"], dict)
    # Bound must hold for the whole retained value, not just the outer dict.
    assert len(json.dumps(digested["value"], separators=(",", ":"))) <= MAX_JSON_CHARS


def test_small_json_passthrough() -> None:
    payload = {"kind": "json", "value": {"k": "short"}}
    assert digest_payload(payload) is payload


def test_single_oversized_scalar_does_not_breach_cap() -> None:
    results = {"n1": {"out": {"kind": "scalar", "value": "A" * 2_000_000}}}
    digested = digest_results(results)
    assert digested["n1"]["out"]["kind"] == "truncated"
    assert len(json.dumps(digested).encode("utf-8")) <= MAX_DIGEST_BYTES


def test_many_moderate_payloads_stay_under_cap() -> None:
    results = {f"n{i}": {"out": {"kind": "scalar", "value": "B" * 4096}} for i in range(50)}
    digested = digest_results(results)
    # Match the implementation's compact serialization (separators=(",", ":"))
    total_bytes = len(json.dumps(digested, separators=(",", ":")).encode("utf-8"))
    assert total_bytes <= MAX_DIGEST_BYTES, f"{total_bytes} > {MAX_DIGEST_BYTES}"
