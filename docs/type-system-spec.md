# The Colony Mind Type System & Connection Validation

This document describes the type system and connection validation logic for the Colony Mind
Python SDK. It is the Epic 3 deliverable, built on
[ADR 0011](./adr/0011-type-model-and-compatibility.md) (the type model and compatibility) and
[ADR 0012](./adr/0012-rules-as-portable-data.md) (rules as portable data). The type system is
nominal with subtype relationships, and `cm.validate()` uses this to check graph connections
for compatibility and structural integrity.

## The type model (nominal + subtype relation)

The Colony Mind type system is **nominal**. A type is a string token; the only relationships are token equality and declared subtype/supertype relations. `"any"` is the explicit TOP / wildcard type, which is a supertype of all registered types and a subtype of nothing else. Every type is implicitly a subtype of `"any"`.

Registered tokens today: `DataFrame`, `ClassifierResult`, `AnovaResult`, `HTML`, `Tensor`, and `any`.

The registry lives in `colonymind/types/` and supports declarative extensibility: an out-of-core package can register new type tokens, mirroring the node registry plugin pattern (ADR 0006). An example stub is provided at `examples/type_plugin_stub/`. The registry and its subtype table serialize to JSON so the frontend requires no Python.

## Compatibility semantics

Compatibility is decided by a pure function `is_compatible(source_type, target_type)` returning one of three outcomes: `COMPATIBLE`, `INCOMPATIBLE`, or `UNKNOWN`.

- **COMPATIBLE** when:
  - `target` is `"any"`
  - `source` is `"any"`
  - `source == target` (exact match)
  - `source` is a registered subtype of `target`

- **UNKNOWN** when: a token is not in the registry (warn, do not block)

- **INCOMPATIBLE** otherwise

| source             | target         | outcome        |
|--------------------|----------------|----------------|
| `DataFrame`        | `DataFrame`    | COMPATIBLE     |
| `HTML`             | `DataFrame`    | INCOMPATIBLE   |
| `anything`         | `any`          | COMPATIBLE     |
| `any`              | `anything`     | COMPATIBLE     |
| `Mystery`          | `DataFrame`    | UNKNOWN        |
| `TimeSeries`       | `DataFrame`    | COMPATIBLE (subtype) † |

† The `TimeSeries → DataFrame` row assumes `TimeSeries` has been registered as a subtype of
`DataFrame` (e.g. `registry.register(TypeDef(token="TimeSeries", supertypes=("DataFrame",)))`).
It is **not** in the shipped default catalog — against the default registry an unregistered
token like `TimeSeries` resolves to `UNKNOWN` (a non-blocking warning), exactly like `Mystery`.

## Cardinality

Each port has a declared `Cardinality.ONE` or `Cardinality.MANY`. A `Cardinality.ONE` IN port rejects a second inbound edge; `Cardinality.MANY` permits fan-in.

## Whole-graph inference

Whole-graph type inference walks the IR in topological order, threading each node's resolved OUT types into downstream IN ports. Each node's `infer_types(node, input_types)` is called to resolve its output types. The default `infer_types` echoes each OUT port's declared `data_type`.

## Validating a graph: `cm.validate`

The headline call `cm.validate(graph) -> Diagnostics` runs inference and checks every edge with the rules engine plus structural cardinality and required-IN checks. It is a `@public_op`, serializable, and inspectable.

`Diagnostics` is JSON-native and contains:
- A list of `Diagnostic` findings
- An `edge_compatibility` map (edge id → `true` / `false` / `null`)

Each `Diagnostic` has:
- `severity` (`"error"` or `"warning"`)
- `code`
- `message`
- Optional fields: `edge_id`, `node_id`, `port_id`, `port_name`, `expected_type`, `actual_type`

Known diagnostic codes:

| code                      | severity  | meaning                             |
|---------------------------|-----------|-------------------------------------|
| `type_incompatible`       | error     | Type mismatch                       |
| `type_unknown`            | warning   | Unregistered type token             |
| `cardinality_violation`   | error     | Cardinality constraint violated     |
| `required_input_unconnected` | error  | Required input port not connected   |

`cm.apply_type_compatibility(graph, diagnostics)` returns a copy of the graph with each `Edge.type_compatible` populated from the verdict map (pure; input graph is not mutated).

## Strictness policy

Structural type mismatches and cardinality violations **HARD-FAIL** (error severity). Unregistered tokens only generate warnings and do not block validation.

`cm.validate` is deliberately separate from `Graph`'s construction-time structural validation so exploratory, half-wired graphs can still be built and inspected on the canvas. `cm.validate` never blocks construction.

## The shared codegen/execute gate

Both `compile_to_code` and `execute` share a single validation gate: `enforce_validation_gate`. Both raise a clear error on an error-severity diagnostic before emitting code or running anything, ensuring that both pure functions reject the same graphs for the same reasons (ADR 0002). Warnings pass through (warn-don't-block).

## Frontend handoff & authority model

The frontend gives instant, best-effort feedback from the shipped rules artifact; this SDK is the authoritative re-validator (server-side). The portable rules artifact is documented in [connection-validation.md](./connection-validation.md) (rules + diagnostics JSON schema shipped under `schema/`).

## Out of scope: tensor dimension inference

Tensor per-DIMENSION shape inference is not implemented here. Structural typing only (`Tensor` → `Tensor` is compatible). Dimension inference is roadmap Epic 10, which specializes this framework.
