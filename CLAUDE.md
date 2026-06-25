# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The project uses [`uv`](https://docs.astral.sh/uv/). CI (`.github/workflows/ci.yml`) runs the
four gates below on Python 3.11 and 3.12 — run them locally before pushing:

```bash
uv sync --locked            # install pinned deps (regenerate lock with `uv lock` after editing pyproject)
uv run ruff check .         # lint
uv run ruff format --check .# format gate (use `uv run ruff format .` to fix)
uv run mypy emergentflow    # type-check
uv run pytest               # full test suite
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
`pyproject.toml`.

## Architecture

Emergent Flow is a visual data/ML platform; this repo is the open-source Python SDK and graph
IR. The system is governed by a set of Architecture Decision Records in `docs/adr/` — **read
the relevant ADR before changing anything cross-cutting**, since the invariants below are
deliberate and expensive to retrofit.

### The two pure functions over one IR (the central invariant)

The graph IR is the single source of truth; Python is a one-way compiled artifact, never
re-parsed back into a graph (ADR 0001). Two pure functions consume that IR:

- `ef.compile_to_code(graph) -> str` (`emergentflow/codegen/compiler.py`) — emits a runnable Python module.
- `ef.execute(graph) -> results` (`emergentflow/codegen/executor.py`) — the in-process reference interpreter.

**ADR 0002 is the hard invariant the whole product rests on:** running the code from
`compile_to_code(ir)` must produce artifacts equivalent to `execute(ir)`. This is enforced
as a CI gate. When you touch a node's `codegen` you must keep its `execute` equivalent (and
vice versa). Both functions must stay **pure** (no I/O, no global state) so Epic 6 can wrap
the executor in sandboxing later; all filesystem I/O lives in `emergentflow/codegen/export.py`.

### Node contract (`emergentflow/nodes/`)

Every node type subclasses `NodeDefinition` (`emergentflow/nodes/contract.py`) and declares
class-level metadata (`type`, `version`, `family`, `ports`, `params`, `paradigm`) plus two
behaviors that must be equivalent by construction:

- `codegen(node, ctx) -> CodeFragment` — `ctx` (a `CodegenContext`, ADR 0009) supplies the
  variable name bound to each IN port and allocated to each OUT port. Nodes **must not**
  hardcode variable names; they ask `ctx.in_var(port)` / `ctx.out_var(port)`. A `CodeFragment`
  is structured (`imports` + `body`) so the whole-graph compiler can de-duplicate imports.
- `execute(node, inputs) -> dict` keyed by OUT-port name.

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
imports families (`ef.data`, `ef.stats`, …), the `ef.codegen` namespace, and the top-level
entry points (`ef.compile_to_code`, `ef.execute`, `ef.export_script`) on first access
(`emergentflow/__init__.py`), so a bare `import emergentflow` stays light.

## Conventions & gotchas

- The SDK package is `emergentflow`, conventionally aliased `ef` — never `omnicanvas`/`oc`.
- ruff line length is 100; the IR enums intentionally subclass `(str, Enum)` (UP042 ignored)
  for stable JSON serialization — don't migrate them to `StrEnum`.
- Generated code must pass `ruff` and be importable; new node types need a golden/equivalence
  test, not just a unit test.
- Contributions go through a license-grant CLA; the `cla` PR check fails until the committer
  comments the sign-off phrase on the PR.
