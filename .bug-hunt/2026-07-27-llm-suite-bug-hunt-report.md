# Bug Hunt Report: LLM tool suite (`emergentflow/llm/`)

## Summary
- Scope reviewed: `emergentflow/llm/` in full (`__init__.py` / `call()` + JSON-schema
  validation, `protocol.py`, `gateway.py`, `replay.py`, `budget.py`, `pricing.py`, `env.py`,
  `secrets.py`, `templating.py`, `aggregate.py`), plus the node wrappers that route through it
  (`nodes/examples/llm_call.py`, `llm_prompt.py`, `llm_prompt_from_file.py`), `eval/run.py`
  (the other direct consumer of `llm.call`), and the existing test suite for all of the above.
- Confirmed findings: 1 High, 1 Low.
- Overall assessment: the seam is unusually well-tested for the pure/deterministic paths
  (`ReplayClient`, `BudgetClient`, templating, pricing, the pre-flight secrets check, and the
  ADR-0002 equivalence tests) — I could not break any of those. The gap is the one path that
  had **no** test coverage at all: `GatewayClient`'s parsing of a real (or realistically-shaped)
  LiteLLM provider response. Feeding it response shapes that real providers actually produce
  (null message content, which happens on tool-call/refusal completions) surfaces an unhandled,
  undocumented exception instead of the client's own `GatewayResponseError` contract.

## Findings

### High — `GatewayClient.complete()` crashes with a raw `TypeError` instead of `GatewayResponseError` when the provider returns null content in JSON mode
- **Status:** FIXED
- **Location:** `emergentflow/llm/gateway.py:120-132` (specifically the `json.loads(content)` call at line 126 and the `except json.JSONDecodeError` at line 127)
- **Class:** Error handling — wrong/incomplete exception type caught
- **Confidence:** Confirmed
- **Description:** When `request.response_format == "json"`, `GatewayClient.complete()` does:
  ```python
  try:
      data = json.loads(content)
  except json.JSONDecodeError as exc:
      raise GatewayResponseError(
          f"Requested response_format='json' but the provider's content "
          f"was not valid JSON: {exc}"
      ) from exc
  ```
  `content` is `choice.message.content`, taken directly off the LiteLLM/OpenAI-shaped
  response with no null check. Real chat-completion responses legitimately carry
  `message.content = None` — e.g. a refusal, a moderation block, or (most commonly) a
  completion that finishes via `tool_calls`/`finish_reason="tool_calls"` with no text content.
  `json.loads(None)` does not raise `json.JSONDecodeError` — it raises `TypeError`, which the
  `except` clause does not catch. The class's own docstring promises `GatewayResponseError`
  is raised "if `response_format == 'json'` and the provider's content was not valid JSON";
  a `None` content is a case of exactly that, but instead a raw `TypeError` propagates,
  uncaught, all the way up through `emergentflow.llm.call()`, the `llm.call` node's
  `execute()`, and (in the served app) the request handler — surfacing as an opaque 500
  instead of the actionable error message the class was designed to give.
- **Evidence / Reproduction:** Installed the real `litellm` package (ad hoc, matching the
  project's own pattern for optional-extra deps in tests — not added to `pyproject.toml`;
  uninstalled again afterward) and monkeypatched `litellm.completion` to return a real
  `litellm.types.utils.ModelResponse` whose message content is `None` (the shape a
  tool-call-only or refusal response actually has):
  ```python
  import litellm, os
  from litellm.types.utils import ModelResponse, Choices, Message, Usage as LUsage
  from emergentflow.llm.gateway import GatewayClient, GatewayResponseError
  from emergentflow.llm.protocol import LLMRequest

  os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"

  def fake_completion(**kwargs):
      return ModelResponse(
          choices=[Choices(finish_reason="tool_calls", index=0,
                            message=Message(content=None, role="assistant"))],
          usage=LUsage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
          model=kwargs["model"],
      )
  litellm.completion = fake_completion

  client = GatewayClient()
  req = LLMRequest(provider="anthropic", model="claude-sonnet-5",
                    messages=({"role": "user", "content": "give json"},),
                    response_format="json")
  client.complete(req)
  ```
  Observed result:
  ```
  UNEXPECTED: TypeError the JSON object must be str, bytes or bytearray, not NoneType
  ```
  instead of the expected `GatewayResponseError`. (Confirmed standalone too:
  `json.loads(None)` raises `TypeError`, not `json.JSONDecodeError`.)
- **Impact:** Any `llm.call` node configured with `response_format="json"` against a
  model/provider that returns a tool-call, refusal, or otherwise content-less completion will
  crash the graph run with an unhandled, confusing `TypeError` rather than the documented,
  actionable `GatewayResponseError`. This is precisely the failure mode the try/except block
  exists to handle gracefully, and it misses the single most common real-world cause of
  "provider didn't give me JSON" (no content at all, vs. malformed content).
- **Remediation:** Guard for `None` explicitly before parsing, or widen the caught exception
  types, e.g.:
  ```python
  if content is None:
      raise GatewayResponseError(
          "Requested response_format='json' but the provider returned no message "
          f"content (finish_reason={finish_reason!r}); there is nothing to parse as JSON."
      )
  try:
      data = json.loads(content)
  except json.JSONDecodeError as exc:
      raise GatewayResponseError(
          f"Requested response_format='json' but the provider's content "
          f"was not valid JSON: {exc}"
      ) from exc
  ```
  Re-running the reproduction above with this fix raises `GatewayResponseError` with a clear,
  actionable message instead of the raw `TypeError`.
- **Fix applied:** the guard above was added at `emergentflow/llm/gateway.py:122-127`.
  Regression coverage added in `tests/test_llm_gateway.py` (new file, `pytest.importorskip`
  ("litellm")-gated, no network calls — monkeypatches `litellm.completion` to return a real
  `litellm.types.utils.ModelResponse`): covers the None-content case (this finding), the
  pre-existing malformed-content case, and a valid-JSON sanity check. Full suite
  (`uv run pytest -q`) passes: 2546 passed, 23 skipped, 0 failed; `ruff check`/`ruff format
  --check`/`mypy emergentflow/llm/gateway.py` all clean.

### Low — `GatewayClient.complete()` raises a raw `IndexError` if the provider response has zero choices
- **Location:** `emergentflow/llm/gateway.py:99` (`choice = response.choices[0]`)
- **Class:** Error handling — unguarded index access
- **Confidence:** Confirmed (as a code defect); real-world reachability is uncertain
- **Description:** `response.choices[0]` is accessed with no length check. If a provider
  response ever comes back with an empty `choices` list, this raises a bare `IndexError`
  instead of the module's own `GatewayResponseError` (the same contract violation as the
  High finding above, on the earlier line).
- **Evidence / Reproduction:** Same harness as above, with `litellm.completion` returning a
  `ModelResponse(choices=[], usage=..., model=...)`:
  ```
  ERR IndexError list index out of range
  ```
- **Impact:** Same class of user-facing crash as the High finding, but I could not confirm
  that any real provider LiteLLM proxies for actually returns an empty `choices` list in
  practice (most provider integrations guarantee at least one choice) — rating Low rather
  than High on that basis. Included because it is the same unguarded-access pattern in the
  same function and trivial to harden alongside the fix above.
- **Remediation:** Guard alongside the content-hardening fix, e.g.:
  ```python
  if not response.choices:
      raise GatewayResponseError("Provider response contained no choices.")
  choice = response.choices[0]
  ```

## Notes & unverified leads
- `GatewayClient.embed()` (`gateway.py:185`) has the same shape of risk
  (`response.data` is typed `Optional[List[...]]` upstream in LiteLLM and is iterated with no
  None-check), but I did not find a realistic path for `litellm.embedding()` to return
  `data=None` on a nominally successful call, so I did not chase this further — noting it only
  as a "same pattern, unconfirmed trigger" item, not a finding.
- `emergentflow/llm/aggregate.py:summarize_run` returns `NaN` for `latency_p50_ms`/
  `latency_p95_ms` when given a zero-row DataFrame (`Series.quantile` on an empty series).
  `ef.eval.run` can produce a zero-row DataFrame (empty `dataset` or `variants`), so this is
  reachable, but `NaN` doesn't crash anything downstream I could find and is arguably the
  mathematically correct answer for "no data" — I could not demonstrate this as a genuine
  defect rather than a reasonable edge-case output, so it stays unconfirmed/not reported.

## Coverage & limitations
- Everything in `emergentflow/llm/` other than `GatewayClient`'s response-parsing logic is
  covered by the existing test suite (`tests/test_llm_*.py`) to a degree I could not find gaps
  in by construction, reading, or targeted adversarial inputs (empty/negative budgets, template
  edge cases, schema-validation edge cases, content-hash stability, fixture round-tripping).
- `GatewayClient` itself has **zero** direct unit tests exercising `complete()`/`embed()`'s
  internal parsing against any response shape (real or mocked) — every existing reference to
  `GatewayClient` in the test suite only checks *that* it gets constructed (or doesn't), never
  what it does with a response. That blind spot is exactly where both findings above live; it
  would be the highest-value place to add coverage next (e.g. a small fixture-backed fake
  `litellm.completion`/`litellm.embedding` per the harness used to verify these findings).
- I did not chase `emergentflow/collab/` agent adapters or `emergentflow/embed/` beyond
  confirming they route through the same `LLMClient`/`GatewayClient` seam — no defects found
  there in a first pass, but they were not adversarially tested to the same depth as
  `emergentflow/llm/` itself, per the task's stated primary scope.
