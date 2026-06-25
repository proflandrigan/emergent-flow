# Codegen Reference Executor & Equivalence (Story 6)

The code-generation engine (`emergentflow.codegen`, Epic 2) commits — per
[ADR 0002](adr/0002-execute-the-ir-not-the-string.md) — to **two pure functions
over one IR**: `ef.compile_to_code(graph) -> str` (Story 5) emits runnable Python,
and `ef.execute(graph) -> results` (Story 6) runs the graph directly. Their
artifacts must be *equivalent*.

## Public surface

```python
import emergentflow as ef

results = ef.execute(graph)   # {node_id: {out_port_name: value}}
```

`execute` is the structural twin of `compile_to_code`: it reuses the same Story 2
plumbing (deterministic `topological_sort` + `build_wiring_map`) and applies the
same guards with the same error messages — a non-`FUNCTIONAL` paradigm raises
`CodegenError`, a dangling required IN port raises `UnboundInputError`. Instead of
emitting a `CodeFragment` per node it calls the node's `execute(node, inputs)`,
threading each OUT-port value to every downstream IN port. The return value is a
mapping from node id to that node's outputs (keyed by OUT-port name) and satisfies
the SDK inspectable-result contract (`emergentflow/api.py`).

## The A2 equivalence invariant

`tests/test_codegen_equivalence.py` enforces ADR 0002's "A2" invariant over a
corpus of graphs. For each graph it:

1. runs `execute(graph)` in-process and canonicalizes every per-port artifact to
   a JSON-native form;
2. compiles the graph and runs the emitted module **as a real subprocess** (the
   genuine "what you see runs" path), dumping the same per-port artifacts via the
   *identical* canonicalizer;
3. asserts the two sides match (float-tolerant, NaN-aware).

The corpus covers the vertical slice (`examples/vertical_slice/pipeline.json`,
fan-out) and the functional pipeline (`examples/functional_pipeline.json`, linear
chain), plus trivial and empty graphs. The broad golden-file fixture corpus and
the formal CI golden gate are Story 9.

### Equivalence boundary: computed values vs rendered documents

Computed data artifacts (DataFrames, the ANOVA and classifier result dataclasses)
are compared **exactly**. Rendered-document artifacts — OUT ports whose
`data_type` is `HTML`, i.e. the ydata-profiling report — embed wall-clock
timestamps and measured durations and so are *not* byte-deterministic even across
two runs of the identical code path; for those the harness asserts **shape parity**
(both sides a non-empty string) rather than byte-equality. The deterministic
computational artifacts are what actually prove `execute` ≡ `compile_to_code`.

## Scope boundary: this is the reference executor, not the runtime

`execute` is a **pure, in-process reference** implementation: no sandboxing, no
resource limits, no streaming, no isolation. It exists to run graphs for tests,
previews, and the equivalence harness. The productionized execution runtime —
which wraps this reference with sandboxing, resource limits, and streaming — is
**Epic 6**. Keeping `execute` pure (no I/O of its own, no global state) is what
lets Epic 6 wrap it without re-architecting.
