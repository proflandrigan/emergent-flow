# Colony Mind Node-Definition Contract

- **Version:** 1
- **Status:** Accepted
- **Date:** 2026-06-16

---

## Overview

Every node type in Colony Mind conforms to one contract so the registry, codegen, executor,
and config UI can all consume it uniformly. The contract has two halves bound by one base
class (see [ADR 0005](adr/0005-node-definition-contract.md)):

- a **serializable spec** — ports, typed params, defaults, validation hints, version — that
  the frontend renders with no Python present (`colonymind/nodes/spec.py`);
- **Python behaviour** — codegen, executor, type-inference — implemented on the
  `NodeDefinition` base class (`colonymind/nodes/contract.py`).

A node *definition* is the catalog template for a node *type*; an IR `Node` (Story 2) is an
*instance* of that type on the canvas. The link between them is the `type` string:
`NodeDefinition.type == NodeSpec.type == Node.type`, which is also the registry lookup key
(Story 4).

Relevant ADRs: [0002 — execute, not the string](adr/0002-execute-the-ir-not-the-string.md),
[0003 — two paradigms](adr/0003-sdk-supports-two-paradigms.md),
[0005 — the contract](adr/0005-node-definition-contract.md).

---

## The serializable spec

All spec models are Pydantic v2 subclasses of `IRModel` (`extra="forbid"`,
`validate_assignment=True`) and round-trip losslessly through JSON.

### NodeSpec

`colonymind.nodes.spec.NodeSpec` — the complete declarative descriptor a definition emits via
`to_spec()`.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `type` | `str` | — | Catalog key, e.g. `"data.load_csv"`. Matches `Node.type`; the registry key. |
| `version` | `int` | `1` | Per-node catalog version (see [Versioning](#versioning)). Must be ≥ 1. |
| `family` | `str` | — | Coarse grouping for catalog/UI, e.g. `"data"`, `"clean"`. |
| `label` | `str` | — | Human-friendly display name. |
| `paradigm` | `Paradigm` | `"functional"` | Execution paradigm (ADR 0003). |
| `ports` | `list[PortSpec]` | `[]` | Declared ports (templates for IR ports). |
| `params` | `list[ParamSpec]` | `[]` | Declared typed params (templates for IR params). |

### PortSpec

`colonymind.nodes.spec.PortSpec` — a declared connection point; the template for an IR `Port`
(no `id`; ids are minted per instance).

| Field | Type | Default | Semantics |
|---|---|---|---|
| `name` | `str` | — | Port name, unique among the node's ports of the same direction (non-empty). IN and OUT may share a name — `execute` keys inputs/outputs in separate namespaces. |
| `direction` | `Direction` | — | `"in"` or `"out"`. |
| `data_type` | `str` | `"any"` | Opaque data-type token (full type system is Epic 5). |
| `cardinality` | `Cardinality` | `"one"` | How many edges may attach (`"one"`/`"many"`). |
| `required` | `bool` | `True` | For IN ports, whether an edge must connect. Ignored for OUT. |
| `label` | `str \| None` | `None` | Optional display label. |
| `help` | `str \| None` | `None` | Optional one-line description. |

### ParamSpec

`colonymind.nodes.spec.ParamSpec` — a declared typed parameter; the template for an IR
`Param` plus the authoring metadata the config UI needs.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `name` | `str` | — | Parameter name, unique within the node (non-empty). |
| `type_token` | `str` | — | Opaque declared-type label, e.g. `"str"`, `"int"` (non-empty). |
| `default` | `ParamValue` | `None` | Default value used when the instance leaves it unset. |
| `required` | `bool` | `False` | Whether a value must be supplied. |
| `label` | `str \| None` | `None` | Optional display label. |
| `help` | `str \| None` | `None` | Optional one-line description. |
| `hints` | `ValidationHints \| None` | `None` | Constraints + widget choice. |

### ValidationHints

`colonymind.nodes.spec.ValidationHints` — every field optional; an unset field imposes no
constraint. Consumed by the Epic 4 config UI and by `validate_node`.

| Field | Type | Applies to | Semantics |
|---|---|---|---|
| `min`, `max` | `float \| None` | numeric values | Inclusive bounds (bools are never treated as numeric). |
| `step` | `float \| None` | numeric widgets | Step increment hint. |
| `choices` | `list[ParamValue] \| None` | any value | Value must be one of these (enum/select). |
| `min_length`, `max_length` | `int \| None` | strings & lists | Inclusive length bounds. |
| `pattern` | `str \| None` | strings | Regex the value must fully match (`re.fullmatch`). |
| `widget` | `str \| None` | UI | Advisory widget hint: `"text"`, `"number"`, `"select"`, `"slider"`, `"checkbox"`, `"file"`. |

---

## The behaviour: `NodeDefinition`

`colonymind.nodes.contract.NodeDefinition` is an abstract base class. A concrete definition
sets the class-level metadata attributes (`type`, `version`, `family`, `label`, `paradigm`,
`ports`, `params`) and implements the behaviour.

### Required (abstract)

- **`codegen(self, node) -> CodeFragment`** — the codegen template. Emits the Python source
  the node contributes. Must be the human-readable equivalent of `execute` for the same node
  (ADR 0002). The output is for display, export, and Git publishing; it is never `exec`-ed in
  production.
- **`execute(self, node, inputs) -> dict`** — the executor. Runs the node directly over its
  IR. `inputs` is keyed by IN-port name; the return is keyed by OUT-port name.

### Optional (overridable)

- **`infer_types(self, node, input_types) -> dict`** — shape/type-inference. The default
  returns each OUT port's declared `data_type`; override when output type depends on inputs or
  params. Full inference is Epic 5.

### Derived (provided; do not override)

- **`to_spec(self) -> NodeSpec`** — the serializable descriptor, derived from the class
  metadata.
- **`instantiate(self, *, label=None, position=None, **param_overrides) -> Node`** — mint a
  fresh, graph-valid IR `Node`: ports from the `PortSpec` list (fresh ids), params from the
  `ParamSpec` list (value = override if given, else the spec default). Unknown override names
  raise `ValueError`.
- **`validate_node(self, node) -> list[str]`** — return human-readable errors (empty = valid):
  type match, required params present, no undeclared params, and each value against its
  `ValidationHints`. Port/edge wiring is validated at the graph level, not here.

### CodeFragment

`colonymind.nodes.contract.CodeFragment` — what `codegen` returns.

| Field | Type | Default | Semantics |
|---|---|---|---|
| `imports` | `list[str]` | `[]` | Import lines; the whole-graph compiler de-duplicates these. |
| `body` | `str` | `""` | Statement(s) implementing the node; binds the node's outputs. |

`render()` returns a self-contained snippet (imports, blank line, body) for previews and
tests; the real compiler renders imports once per graph.

---

## Versioning

Two independent version axes exist; do not conflate them:

- **`Graph.schema_version`** (`CURRENT_SCHEMA_VERSION`) — the IR *wire format* for an entire
  graph. Bumped when the serialized graph shape changes.
- **`NodeDefinition.version`** — one *node type's* contract. Bumped on any contract-affecting
  change to that node (params added/removed, codegen/executor semantics changed).

Story 9 migrations key off both. Policy (per Epic 1): no contract-affecting node change ships
without a `version` bump, and no breaking schema change ships without a migration step.

---

## Conformance summary

A node type conforms to the contract when it:

1. subclasses `NodeDefinition` and sets `type`, `family`, `label` (and `version`/`paradigm`
   as needed);
2. declares its `ports` (`PortSpec`) and `params` (`ParamSpec`, with defaults + hints);
3. implements `codegen` and `execute` such that they are equivalent (ADR 0002);
4. overrides `infer_types` where output type is not simply the declared OUT-port type.

See [`authoring-a-node.md`](authoring-a-node.md) for a step-by-step walkthrough, and
`colonymind/nodes/examples/` for two reference implementations.
