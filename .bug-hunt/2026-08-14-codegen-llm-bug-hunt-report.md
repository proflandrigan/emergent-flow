# Bug Hunt Report: emergent-flow Python SDK (codegen / llm / clients / script / api)

## Summary
- **Scope reviewed:** `emergentflow/codegen/` (traversal, wiring, naming, context, compiler,
  executor, formatting, declarative, export, composite), `emergentflow/clients.py`,
  `emergentflow/llm/` (gateway, replay, budget, call, protocol, pricing), `emergentflow/script/`,
  and `emergentflow/api.py`.
- **Confirmed findings: 0.** No bug was reproduced.
- **Overall assessment:** The reviewed modules are robust. The central ADR-0002 invariant
  (`compile_to_code(ir)` ≡ `execute(ir)`), the naming/topo-sort/context plumbing, import
  de-duplication, the graph-param path, the composite boundary seam, the LLM budget/replay
  logic, `run_code` isolation, and `is_inspectable` all held up under targeted edge-case probing
  and differential fuzzing. Nothing met the "prove it before you report it" bar.

## Verification performed (all green)

Baseline: `uv run pytest -m equivalence -q` → **331 passed, 19 skipped**. The named test files
(`test_codegen_naming.py`, `test_codegen_traversal.py`, `test_api_conventions.py`,
`test_llm_budget.py`, `test_script_run_code.py`, `test_codegen_formatting.py`) also pass.

Differential escalation beyond the existing test corpus (harness under `/tmp/opencode/`):

1. **Real compiled `main()` vs `execute()`** (the equivalence gate only runs `_assemble`'s body,
   never the emitted `main()`); checked empty graph, single node, disconnected nodes,
   fan-in/out diamond with MANY ports, naming-collision labels, note-only graphs, and graph-param
   graphs. All agreed; all rejections agreed.
2. **Random functional DAG fuzzer** (`fuzz_equiv.py`): 3000 graphs (sources, binary adders, MANY
   fan-in sums, duplicate labels, `-`/space/digit slugs) — **0** rejection divergences and **0**
   value divergences between `execute` and the compiled body over every OUT port.
3. **Naming fuzzer** (`fuzz_naming.py`): 20,000 random (label, port) combinations built via
   `build_name_map` — no duplicate var names, no invalid identifiers, no keyword collisions.
4. **Duplicate IN/OUT port names**: separate `in_vars`/`out_vars` dicts in `context.py` handle it;
   both paths consistent.
5. **Cycle detection** re-verified; **empty graph** and **single node** compile/run identically.
6. **Graph-level params** end-to-end via the real `main(*, amount=9)` + `execute(params=...)` —
   exact match including overrides.
7. **Composite MANY boundary** (area of the previously-fixed executor divider) — once the
   composite's exposed IN port is correctly declared `Cardinality.MANY`, `execute` and compiled
   `main()` both return `[1]`; identical. (A one-IN-port MANY boundary where a non-list seeded
   value is passed to a node that `sum()`s iterates identically crashes on BOTH sides — no
   divergence.)
8. **`run_code` namespace isolation**: a secret left by one invocation is invisible to the next
   and to the importing module (`NameError` on a re-read) — no leak.
9. **Replay round-trip** (`write_fixture` → `ReplayClient.complete`) is exact for `data`
   dicts, `None` text, schema, and cost; `content_hash` is stable across identical requests.
10. **Budget client**: the "allow first call, trip after ceiling" semantics are intentional and
    match `tests/test_llm_budget.py`.

## Notes & unverified leads (explicitly NOT findings)

- **`is_inspectable` accepts any dataclass instance without recursing into its fields** —
  `is_inspectable` returns `True` for a dataclass even when a field holds a non-serializable
  object (e.g. `io.StringIO`). This is a documented, deliberate design choice (the module
  docstring and `tests/test_api_conventions.py::test_dataclass_instance_is_inspectable` both
  bless "dataclass instance" wholesale), and the SDK depends on it (e.g. timeseries
  `ForecastResult` pairs a tidy summary with a live statsmodels object). Since it is the
  documented contract rather than an accidental gap, I did not classify it as a finding, but it
  is the one place where the "serializable + inspectable" promise is softer than the docstring
  states. Would require a product decision to change, not a casual fix.

- I could not exercise the live `GatewayClient` (needs the optional `litellm` extra + a network
  provider), so its LiteLLM response parsing was reviewed statically only; prior tree reports
  already cover a None-`content` `json.loads` (None) path there.

## Coverage & limitations
- Review was read-only; no repository edits (probes live under `/tmp/opencode/`, now removable).
- The `data/warehouse` (ADR 0018) and `data/http` (Epic 16) client backends were out of scope;
  only their threading through `clients.py`/the compiler preamble was inspected.
- The modern declarative seam requires `torch` (lazy-imported); its runtime-equivalence was not
  dynamically exercised here (those equivalence tests are among the 19 deliberately skipped).