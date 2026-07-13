# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The project uses [`uv`](https://docs.astral.sh/uv/) for the Python SDK/server and `npm` for the
`ui/` canvas. CI (`.github/workflows/ci.yml`) has three jobs — a Python matrix (3.11/3.12), a UI
job, and a live-Postgres driver-integration job — run the Python gates and the UI gates locally
before pushing:

```bash
uv sync --locked            # install pinned deps (regenerate lock with `uv lock` after editing pyproject)
uv run ruff check .         # lint
uv run ruff format --check .# format gate (use `uv run ruff format .` to fix)
uv run mypy emergentflow    # type-check
uv run pytest               # full test suite
uv run pytest -m equivalence -q   # ADR-0002 compile_to_code(ir) == execute(ir) gate, also covered by the full suite
```

If you change IR models, a node's `spec`, or the mutation/session-event schemas, regenerate the
contract artifacts the `ui/` build consumes and verify the UI boundary is intact — both are CI
gates:

```bash
uv run python scripts/export_ui_contracts.py   # regenerates ui/src/generated/*.json
uv run python scripts/check_ui_boundary.py      # fails if ui/ imports emergentflow
```

Single test / subset:

```bash
uv run pytest tests/test_codegen_compiler.py            # one file
uv run pytest tests/test_codegen_compiler.py::test_name # one test
uv run pytest -k declarative                            # by keyword
```

`torch` is intentionally **not** a dependency. Tests that exercise the declarative
`execute` path use `pytest.importorskip("torch")` and skip when it's absent. To run them,
install torch into the venv ad hoc (`uv pip install torch`) — do not add it to
`pyproject.toml`. The same lazy-import pattern applies to other optional extras used only in
specific tests: `litellm` (`[llm]`), `fastmcp` (`[mcp]`, though it's in the dev dependency
group so it's present in CI), the Bayesian stack `pymc`/`bambi`/`arviz` (`[bayes]`), and
`shap` (`[explain]`).

### UI (`ui/`)

```bash
cd ui
npm ci               # install pinned deps
npm run dev          # Vite dev server (proxies API calls to a locally running `emergentflow serve`)
npm run lint         # eslint .
npm run typecheck    # tsc --noEmit
npm test             # vitest run
npm run build        # emits the production bundle into ../emergentflow/_static/
npm run gen:types    # regenerate ui/src/generated/ir.ts from ir.schema.json — run after export_ui_contracts.py
```

`ui/` MUST NOT `import` or bundle `emergentflow` (enforced by `scripts/check_ui_boundary.py` in
CI) — it talks to `emergentflow/server/` only over localhost REST/SSE, using the four exported
contract artifacts (IR JSON Schema, node catalog, `GraphMutation` schema, session-event schema).

### Running the app end to end

```bash
uv run emergentflow serve     # boots the local FastAPI/Uvicorn server + bundled canvas at :8765 (alias: `emergentflow lab`)
curl http://127.0.0.1:8765/healthz
```

See [`docs/runbook.md`](./docs/runbook.md) for the full walkthrough (canvas UX, REST/SSE API,
driving the SDK directly in Python).

## Architecture

Emergent Flow is a visual data/ML platform shipped as **one repo, one bundled
`pip install emergentflow[server]`**: the open-source Python SDK + graph IR (`emergentflow/`),
a bundled local server (`emergentflow/server/`), and a React canvas (`ui/`) that talks to the
server only over localhost REST/SSE and never imports the Python package (ADR 0013). A bare
`pip install emergentflow` installs the SDK for programmatic use; the `[server]` extra adds
FastAPI/Uvicorn for the canvas. The system is governed by a set of Architecture Decision
Records in `docs/adr/` — **read the relevant ADR before changing anything cross-cutting**,
since the invariants below are deliberate and expensive to retrofit.

### The two pure functions over one IR (the central invariant)

The graph IR is the single source of truth; Python is a one-way compiled artifact, never
re-parsed back into a graph (ADR 0001). Two pure functions consume that IR:

- `ef.compile_to_code(graph) -> str` (`emergentflow/codegen/compiler.py`) — emits a runnable Python module. For a graph with a `requires_client` node, the emitted `main()` itself takes a `client` param (ADR 0017) — `compile_to_code` stays a pure function of `graph` alone; only the *emitted code's* entry point is parametrized by a client.
- `ef.execute(graph, *, client=None) -> results` (`emergentflow/codegen/executor.py`) — the in-process reference interpreter.

**ADR 0002 is the hard invariant the whole product rests on:** running the code from
`compile_to_code(ir)` must produce artifacts equivalent to `execute(ir)`. This is enforced
as a CI gate. When you touch a node's `codegen` you must keep its `execute` equivalent (and
vice versa). Both functions must stay **pure** (no I/O, no global state) so Epic 6 can wrap
the executor in sandboxing later — I/O is quarantined at the edges, never inline in the two
core functions: filesystem export I/O lives in `emergentflow/codegen/export.py`, and network
I/O for effectful nodes (LLM calls, ADR 0017) lives inside an injected `LLMClient` — `execute`
takes an optional `client` param and stays a pure function of `(ir, client)`; `compile_to_code`
stays a pure function of `ir` alone and instead emits a module whose *own* entry point takes
`client`, so the impurity is pushed one level further out, to whoever runs the compiled code.
A node sets `requires_client = True` to receive the client either way (see Node contract
below for the caller-side obligation this creates). `GatewayClient`
(`emergentflow/llm/gateway.py`) makes the real network call; `ReplayClient`
(`emergentflow/llm/replay.py`, fixture record/replay keyed by request content-hash) is the
default in tests and the equivalence gate, so CI never touches the network.

### Node contract (`emergentflow/nodes/`)

Every node type subclasses `NodeDefinition` (`emergentflow/nodes/contract.py`) and declares
class-level metadata (`type`, `version`, `family`, `ports`, `params`, `paradigm`) plus two
behaviors that must be equivalent by construction:

- `codegen(node, ctx) -> CodeFragment` — `ctx` (a `CodegenContext`, ADR 0009) supplies the
  variable name bound to each IN port and allocated to each OUT port. Nodes **must not**
  hardcode variable names; they ask `ctx.in_var(port)` / `ctx.out_var(port)`. A `CodeFragment`
  is structured (`imports` + `body`) so the whole-graph compiler can de-duplicate imports.
- `execute(node, inputs) -> dict` keyed by OUT-port name. A node with
  `requires_client = True` (ADR 0017) instead takes `execute(node, inputs, *, client) -> dict`
  and its `codegen` threads the compiled module's injected `client` param through — both paths
  route through the same `emergentflow.llm.call`/`emergentflow.eval.run`-style wrapper so the
  ADR-0002 equivalence holds by construction. Any caller that walks the node graph directly
  (the server, a future CLI) must check `requires_client` and pass a client itself; it is not
  implied by the base `execute(node, inputs)` signature.

Nodes self-register via the `@register` decorator; importing `emergentflow.nodes` fires every
reference node's registration. Reference nodes live in `emergentflow/nodes/examples/` and route
both `codegen` and `execute` through the same `ef.*` family wrapper, which keeps the ADR-0002
equivalence true by construction. Per-node `version` (a contract version) is distinct from
`Graph.schema_version` (the wire format) — bump `version` on any codegen/param change.

### Two paradigms (ADR 0003)

`compile_to_code` and `execute` both dispatch on `graph.paradigm`:

- **FUNCTIONAL** — a flat DAG of calls, emitted as string-template statements (ADR 0008),
  assembled in deterministic topological order.
- **DECLARATIVE** — an `nn.module` node owning a subgraph of layers, compiled into an
  `nn.Module` class via **libcst** (`emergentflow/codegen/declarative.py`). This is a narrow
  *seam*: only `nn.module`/`nn.linear`/`nn.relu` are wired, only single linear chains are
  supported, and agent/LangGraph targets and the full layer catalog raise `CodegenError`
  pointing at Epic 10/11. `_prepare_declarative` is the single validation gate shared by both
  the compiler and executor so the two paths accept/reject identical graphs.

### Codegen pipeline composition

The compiler composes small, independent passes (all in `emergentflow/codegen/`), each
deterministic so output is stable for golden tests:

`traversal.py` (topo sort + cycle detection) → `wiring.py` (each IN port → upstream OUT
port) → `naming.py` (readable, collision-free variable names from node labels) →
`context.py` (per-node `CodegenContext`) → `compiler.py` (assemble) → `formatting.py`
(`format_source` runs `ruff` import-organize + format on every emitted module, both
paradigms).

### Public API contract

Public operations are decorated with `@public_op` (`emergentflow/api.py`), which enforces on
every call that the return value is **serializable + inspectable** (`is_inspectable`:
JSON-native, Pydantic model, dataclass, tidy DataFrame, or containers thereof) — a bare
object or live torch module will raise `InspectableContractError`. The `ef` namespace lazily
imports families (`ef.data`, `ef.clean`, `ef.stats`, `ef.ml`, `ef.viz`, `ef.reports`, `ef.llm`,
`ef.eval`, `ef.explain`, `ef.script`), the `ef.codegen` namespace, and the top-level entry
points (`ef.compile_to_code`, `ef.execute`, `ef.export_script`, `ef.validate`) on first access
(`emergentflow/__init__.py`), so a bare `import emergentflow` stays light.

### Injected effectful clients: LLM nodes and data warehouses

Two node families do real, non-deterministic, credentialed network I/O — LLM calls
(`emergentflow/llm/`, ADR 0017) and data-warehouse queries (`emergentflow/data/warehouse/`,
ADR 0018: DuckDB, Postgres, BigQuery, Redshift). Both follow the same seam so the ADR-0002
equivalence gate stays value-exact and offline in CI: a `requires_client = True` node receives
its client through `execute(graph, *, client=...)` / the compiled module's `main(client=...)`,
never by calling out directly. `GatewayClient`/a real warehouse driver makes the live call;
`ReplayClient`/fixture-recorded adapters (content-hash-keyed) are the default in tests and CI.
Credentials never enter the IR — a node carries an env-var *name* (e.g. `api_key_env`) or a
named connection profile, never a literal key/DSN. See `emergentflow/clients.py` for how the
per-node client bundle is assembled and threaded through both `execute` and codegen.

### Model explainability (`emergentflow/explain/`, ADR 0020)

SHAP-based feature attribution and diagnostic plots over an already-fitted `ml.FittedModel`.
Requires the optional `[explain]` extra for SHAP-backed operations; error-analysis and
diagnostic plots (residuals, calibration, ROC/PR, predicted-vs-actual) need no extra deps
beyond the SDK's existing hard deps. Tests use `pytest.importorskip("shap")`.

### Custom code (`emergentflow/script/`)

A `custom_code` node lets users write a `def transform(value):` function that is compiled
and executed in a fresh namespace via `compile()`/`exec()`. Intentionally unsandboxed (same
trust level as the local server). The `run_code()` wrapper mirrors how `ef.llm.call` delegates
to an injected client. The codegen path uses AST-based renaming to wire the transform
function's parameter to the upstream variable name.

### Stats node families

Statistical modeling nodes are split into dedicated per-family node types rather than a single
`fit_model` node: `fit_linear_regression`, `fit_glm`, `fit_gam`, `fit_mixed_model`, and
`fit_bayesian_model`. Each wraps its corresponding `ef.stats.*` function and carries
family-specific params. The old `fit_model` node has been removed.

### Feature transforms

Dedicated transform nodes for feature engineering: `scale_features` (StandardScaler/
MinMaxScaler/RobustScaler), `encode_categorical` (OneHotEncoder/OrdinalEncoder/TargetEncoder),
`discretize` (KBinsDiscretizer), and `generate_features` (PolynomialFeatures/interaction
terms). All route through scikit-learn and follow the standard node contract.

### Local server (`emergentflow/server/`)

A FastAPI/Uvicorn app (optional `[server]` extra; `emergentflow serve` / `emergentflow lab`)
that calls the two pure functions in-process — no Celery, no Redis, no sandboxing. Core routes
(`/compile`, `/execute`, `/execute_node`, `/execute/stream` (SSE), `/validate`, `/compile-spec`,
`/catalog`, `/schema`, `/connections/*`, `/reports/{hash}`, `/export/*`) are stateless: every
request carries the whole graph IR. `/execute/stream` backs the canvas's incremental,
DAG-aware on-disk execution cache (`emergentflow/server/cache.py`) and per-node progress.

### Agent collaboration (`emergentflow/collab/`, ADR 0019)

An **additive, opt-in** layer that lets an AI agent (Claude Code, Gemini, Codex, OpenCode, or
any HTTP client) co-author a graph with a human on the same canvas — see
[`agents/emergent-flow-collaborator.md`](./agents/emergent-flow-collaborator.md) for the
agent-facing protocol. Collaboration state (`GraphSession`, `GraphMutation` proposals, review
threads, gates, the knowledge base) lives **beside** the `Graph` IR, never on it — no `Graph`
field, no `CURRENT_SCHEMA_VERSION` bump. Sessions are served under `/sessions/*` (session-scoped
auth via a bearer token) with an SSE event stream at `/sessions/{id}/events`; a pure
`apply_mutation` function applies a proposed `GraphMutation` to a `Graph`. The canvas includes
an in-app agent chat panel (`ui/src/session/ChatModal.tsx`) backed by a server-side chat runner
(`emergentflow/collab/chat_runner.py`) and pluggable agent adapters
(`emergentflow/collab/agents/`) for Claude, Gemini, Codex, and OpenCode. The **works-without-
agents invariant** is a regression-tested requirement: the base install gains zero new hard
dependencies, `emergentflow/collab/` is never eagerly imported, CI never calls a live LLM, and
existing route contracts stay byte-identical whether or not any session is ever opened. An
optional MCP tool wrapper over the same routes lives in `emergentflow/collab/mcp.py` (`[mcp]`
extra, FastMCP).

### Connection profiles (`emergentflow/connections/`)

A unified, secret-free connection-profile store (`~/.config/emergentflow/connections.toml`)
shared by warehouse (ADR 0018) and LLM (ADR 0017) node families. A profile carries
coordinates and auth-method metadata but **never a credential value** — only env-var names.
The canvas exposes a unified connection manager (`ui/src/connections/`) for warehouse, LLM,
and coding-agent profiles, backed by CRUD routes on the server.

## Conventions & gotchas

- The SDK package is `emergentflow`, conventionally aliased `ef` — never `omnicanvas`/`oc`.
- ruff line length is 100; the IR enums intentionally subclass `(str, Enum)` (UP042 ignored)
  for stable JSON serialization — don't migrate them to `StrEnum`.
- Generated code must pass `ruff` and be importable; new node types need a golden/equivalence
  test, not just a unit test.
