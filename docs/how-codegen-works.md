# How Codegen Works (Epic 2 overview)

Colony Mind compiles a graph IR to Python two ways, and guarantees the two
agree. This is the orientation doc for the code-generation engine
(`colonymind/codegen/`); for component detail see [the compiler](codegen-compiler.md),
[the declarative seam](codegen-declarative.md), [the executor](codegen-executor.md),
and [traversal](codegen-traversal.md).

## Two pure functions over one IR

Per [ADR 0002](adr/0002-execute-the-ir-not-the-string.md), the engine commits to
**two pure functions over one IR**: `cm.compile_to_code(graph) -> str`
(`colonymind/codegen/compiler.py`) emits a runnable Python module, and
`cm.execute(graph) -> results` (`colonymind/codegen/executor.py`) runs the same
graph directly in-process. Their artifacts must be equivalent — the "A2"
invariant — so running the code produced by `compile_to_code(ir)` must yield the
same per-port results as `execute(ir)`. Both functions are pure: no I/O, no
global state, and no hidden coupling to each other beyond the shared IR they
read. This is what lets the generated Python serve as a faithful, inspectable
artifact while the platform itself can choose to execute the IR directly.

## The functional compile pipeline

`compile_to_code` assembles `Paradigm.FUNCTIONAL` graphs through a chain of small,
deterministic passes, each its own module under `colonymind/codegen/`:
`traversal.py` (topological sort + cycle detection) feeds `wiring.py` (resolving
each IN port to its upstream OUT port), which feeds `naming.py` (deriving
readable, collision-free variable names from node labels), which feeds
`context.py` (building a per-node `CodegenContext`), which `compiler.py` uses to
assemble the module, before `formatting.py` normalizes the result. Nodes never
hardcode variable names; a node's `codegen` asks its `CodegenContext` for
`ctx.in_var(port)` / `ctx.out_var(port)` to learn the names the compiler already
allocated. Because every pass is deterministic — stable topo-sort tie-breaks,
stable name-collision suffixing — the same IR always compiles to byte-identical
code, which is exactly what makes golden-snapshot testing possible. See
[ADR 0008](adr/0008-codegen-templating-vs-ast.md) for the templating-vs-AST
decision and [ADR 0009](adr/0009-codegen-binding-context.md) for the binding
context.

## Two paradigms

Both `compile_to_code` and `execute` dispatch on `graph.paradigm`, per
[ADR 0003](adr/0003-sdk-supports-two-paradigms.md). `Paradigm.FUNCTIONAL` graphs
are emitted as a flat sequence of string-template statements wrapped in a
`def main() -> dict[str, object]:` function. `Paradigm.DECLARATIVE` graphs delegate to
`compile_declarative` (`colonymind/codegen/declarative.py`), which compiles an
`nn.module` node's subgraph into an `nn.Module` subclass using a real **libcst**
concrete syntax tree rather than string splicing — see
[the declarative seam](codegen-declarative.md) for a worked example. Despite the
different assembly strategy, both paradigms share the same final `ruff format`
pass before `compile_to_code` returns.

## Quality gates

Story 9 backs the "what you see runs" promise with gates that all run under the
existing `uv run pytest` CI step. Golden-snapshot tests (via syrupy) cover the
functional corpus in `tests/test_codegen_golden.py`, the declarative case in
`tests/test_codegen_declarative.py`, and a reconverging-diamond case in
`tests/test_codegen_equivalence.py`; regenerate them with
`uv run pytest --snapshot-update`. The A2 equivalence gate, also in
`tests/test_codegen_equivalence.py` and marked `@pytest.mark.equivalence` (run in
isolation with `uv run pytest -m equivalence`), compiles each corpus graph, runs
the emitted module as a real subprocess, and asserts its per-port artifacts equal
`execute(ir)`'s. The corpus quality gate (`tests/test_codegen_corpus_quality.py`)
asserts every shippable example graph's generated code is ruff-clean and
parseable. Together these exercise a fixture corpus spanning a linear chain
(`examples/functional_pipeline.json`), a fan-out
(`examples/vertical_slice/pipeline.json`), a declarative subgraph
(`examples/declarative_module.json`), and a reconverging diamond built
programmatically in the equivalence test module.

## What isn't expressible yet

The reference node catalog is honestly single-input today: every reference
node's IN ports are declared `Cardinality.ONE`, and no reference node accepts
two inputs, so a true fan-in or reconverging *join* cannot yet be expressed with
shipped nodes — wiring more than one edge onto a `Cardinality.ONE` port raises a
hard `CardinalityError`. The compiler's fan-in wiring logic is nonetheless
already exercised today by a test-only two-input join fixture (`_EquivJoin2`) in
the equivalence test suite, proving the plumbing works ahead of the catalog.
Multi-input node families — joins, merges, and similar — arrive with the broader
node catalog in Epic 10 and beyond.
