# Bug Hunt Report: Emergent Flow full codebase (2026-08-14)

## Summary

- **Scope reviewed:** The `emergentflow/` Python SDK/server/collab/recommend/stats/
  timeseries/llm/warehouse/codegen + the `ui/` TypeScript layers touched by recent
  commits. Focus was on the freshest, arithmetic-/boundary-/concurrency-heavy code
  and the ADR-0002 (codegen/executor equivalence) seams.
- **Confirmed findings:** 1 Low.
- **Overall assessment:** This codebase is exceptionally well-audited — the two most
  recent commits closed 19 bugs with regression tests, and the full suite (3813 tests,
  ruff, mypy, and the ADR-0002 equivalence gate) is green. An extensive sweep of the
  core compiler, executor, mutation protocol, recommend family (metrics/splits/
  interactions/sequences/transforms), stats family (correlation/co_missingness/EDA/
  funnel/cohort), timeseries transforms, LLM budget/replay, warehouse adapters/spec
  compiler, and collab digest surfaced exactly one reproducible defect: the collab
  JSON digest flags a payload as `truncated` without actually truncating it. Every
  other lead investigated resolved as correct-by-design or was a worthwhile-but-
  already-fixed defect.

## Findings

### LOW — collab JSON digest flags `truncated: True` but returns the full untruncated value

- **Location:** `emergentflow/collab/digest.py:62-72`
- **Class:** Contract violation (documented behavior vs. implementation)
- **Confidence:** Confirmed
- **Description:** `digest_payload` for `kind == "json"` computes the serialized JSON
  size and, when it exceeds `MAX_JSON_CHARS` (1024), returns a digest with
  `"truncated": True` — but the returned `"value"` is the **original, untruncated**
  value. Its own module docstring and `MAX_JSON_CHARS` comment state "JSON payloads
  larger than this get truncated," which the code does not do. A 512KB JSON value was
  carried through whole behind a `truncated: true` flag.
- **Evidence / Reproduction:**
  ```
  >>> from emergentflow.collab.digest import digest_payload, MAX_JSON_CHARS
  >>> huge = {"deep": {"nested": "x" * (MAX_JSON_CHARS * 10)}}
  >>> d = digest_payload({"kind": "json", "value": huge})
  >>> d["truncated"]
  True
  >>> len(str(d["value"]))  # carried through in full, not truncated
  512022
  ```
  The overall `digest_results` 50KB hard cap still bounds the final document (a single
  oversized node collapses to a `truncated` marker), so real system-level context
  admission is protected — impact is confined to `digest_payload`'s documented per-kind
  boundary (used directly for nested `record` fields), a misleading flag, and a JSON
  value occupying the entire remaining digest budget while advertised as truncated.
- **Impact:** A caller reading the digest directly trusts `truncated: True` and can
  receive the full multi-hundred-KB value; the per-kind truncation the public API
  documents is a no-op.
- **Remediation:** Actually bound the retained value. `digest.py` now carries
  `_truncate_json(value, MAX_JSON_CHARS)`, which recursively shortens leaf strings and
  drops trailing collection members, keeping `value` a valid JSON object (no
  invalid-JSON-prefix regression) and verifies via a tightening loop that the result
  serializes under the cap before returning. Regression tests added in
  `tests/test_collab_digest.py`.

## Notes & unverified leads

None reproducible. Leads investigated and closed as **not defects** (each verified via
repro or code trace):

- `apply_mutation`'s `cascade_index += 1` after `_next_cascade_position` appears to
  double-advance; traced: positions still come out correctly spaced (60,60),(120,120),…
  and a skipped free slot on collision is cosmetic (canvas re-lays out anyway).
- Recency-weighting timezone mixing, `correlation`/`co_missingness` dense guards, the
  `_ndcg_at_k`/`_average_precision_at_k` duplicate-item handling, `temporal_split`/`random_split`
  empty-half clamping, `optimize_threshold`'s `precision_recall_curve` tail, and the
  `AdapterWarehouseClient` timeout thread all behaved correctly under crafted inputs.
- `serve()` opens the browser even if the probe times out; best-effort by design.

## Coverage & limitations

- Prior hunts are voluminous (`.bug-hunt/` holds ~42 dated reports); deep review focused
  on code changed in the last ~5 commits plus the most bug-prone arithmetic/edge paths,
  not an exhaustive line-by-line re-derivation of every module.
- The two pure functions (`compile_to_code`/`execute`) and their ADR-0002 equivalence are
  heavily guarded by an existing equivalence gate that passes; I did not find a new
  divergence.
- Live-network paths (LLM `GatewayClient`, cloud warehouse adapters, HTTP client) were not
  exercised against real providers/endpoints; those are gated behind fixtures/ReplayClient
  in CI.
