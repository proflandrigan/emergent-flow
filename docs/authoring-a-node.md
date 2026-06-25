# How to Author a Node

This guide walks through writing a node that conforms to the Emergent Flow node-definition
contract. For the full field reference see [`node-contract-spec.md`](node-contract-spec.md);
for the rationale see [ADR 0005](adr/0005-node-definition-contract.md). We build up the
`clean.impute_missing` reference node (`emergentflow/nodes/examples/impute.py`) step by step.

## Mental model

A **node definition** is the catalog template for a node *type*. It has two halves:

- a **serializable spec** — ports, params, defaults, validation hints, version — that the
  config UI renders with no Python present;
- **behaviour** — how the node compiles to code (`codegen`) and how it runs (`execute`).

You declare the first half as class attributes and implement the second as methods on a
subclass of `NodeDefinition`.

## Step 1 — Subclass `NodeDefinition` and set the metadata

```python
from emergentflow.nodes.contract import NodeDefinition

class ImputeMissing(NodeDefinition):
    type = "clean.impute_missing"   # catalog key; equals Node.type; registry lookup key
    version = 1                     # per-node version (NOT Graph.schema_version)
    family = "clean"                # coarse grouping for catalog/UI
    label = "Impute Missing"        # display name
    # paradigm defaults to Paradigm.FUNCTIONAL
```

Pick `type` as `"<family>.<verb_noun>"`. Bump `version` whenever you later change this node's
params or the meaning of its codegen/executor.

## Step 2 — Declare ports

Ports are templates (`PortSpec`) — no ids; ids are minted per instance. Mark IN ports
`required=False` if the node can run without them.

```python
from emergentflow.ir.common import Direction
from emergentflow.nodes.spec import PortSpec

    ports = [
        PortSpec(name="table", direction=Direction.IN, data_type="Table",
                 help="The input table whose missing cells should be filled."),
        PortSpec(name="table", direction=Direction.OUT, data_type="Table",
                 help="The table with missing cells imputed."),
    ]
```

`data_type` is a token from the type registry; it drives connection-compatibility checks
during `ef.validate`. See Step 6 and [type-system-spec.md](type-system-spec.md) for how to
choose, register, and infer types.

## Step 3 — Declare typed params, with defaults and validation hints

`ParamSpec` carries the value contract; `ValidationHints` carries the constraints and the UI
widget choice. These are what the Epic 4 config UI renders and what `validate_node` enforces.

```python
from emergentflow.nodes.spec import ParamSpec, ValidationHints

    params = [
        ParamSpec(name="strategy", type_token="str", default="mean",
                  label="Strategy", help="How to compute each column's fill value.",
                  hints=ValidationHints(choices=["mean", "median", "most_frequent"],
                                        widget="select")),
        ParamSpec(name="columns", type_token="list[str]", default=None,
                  label="Columns", help="Columns to impute; empty/unset imputes all.",
                  hints=ValidationHints(widget="text")),
    ]
```

Set `required=True` for params with no usable default (e.g. `data.load_csv`'s `path`).

## Step 4 — Implement `execute`

`execute` runs the node directly over the IR. `inputs` is keyed by IN-port name; return a dict
keyed by OUT-port name. Read param values off `node.params`.

```python
    def execute(self, node, inputs):
        strategy, columns = self._args(node)        # pull values off node.params
        table = inputs["table"]
        return {"table": impute_missing(table, strategy=strategy, columns=columns)}
```

Keep the real work in a small, importable helper (`impute_missing`) — see the next step.

## Step 5 — Implement `codegen`, and keep it equivalent to `execute`

`codegen` takes the node *and* a `CodegenContext` (`ctx`), and returns a `CodeFragment`
(`imports` + `body`). The body must bind the node's outputs via `ctx.out_var(<out port
name>)` and read its inputs via `ctx.in_var(<in port name>)` rather than hardcoding `table`.
The whole-graph compiler supplies `ctx` (ADR 0009), resolving each IN port to the variable its
upstream node was allocated and each OUT port to the variable this node is allocated; for a
standalone preview, `ctx` maps each port to its own name. **ADR 0002 requires codegen and
execute to be equivalent.** The cheapest way to guarantee that — and the Story 7 "thin wrapper"
pattern — is to have both call the *same* runtime helper:

```python
    def codegen(self, node, ctx):
        strategy, columns = self._args(node)
        return CodeFragment(
            imports=["from emergentflow.nodes.examples.impute import impute_missing"],
            body=(
                f"{ctx.out_var('table')} = impute_missing("
                f"{ctx.in_var('table')}, strategy={strategy!r}, columns={columns!r})"
            ),
        )
```

`execute` calls `impute_missing(...)`; the emitted code calls the same function. They cannot
drift. Add a test that runs both and asserts equal results — for `codegen`, that means running
`preview().render()` (see
`tests/test_reference_nodes.py::TestImputeMissing::test_codegen_matches_execute`).

## Step 6 — (Optional) override `infer_types`

A node's output ports declare their `data_type`, which is a token from the nominal type
registry (`emergentflow/types/`). Built-in tokens include `DataFrame`, `ClassifierResult`,
`AnovaResult`, `HTML`, `Tensor`, and `any` (the wildcard top type). Prefer reusing an existing
token so connections type-check against other nodes. Use `"any"` only when the port genuinely
accepts anything.

If you need a new token, register it by declaring a `TypeDef` in the registry, optionally
specifying supertypes for subtype compatibility:

```python
from emergentflow.types.registry import TypeDef, registry
registry.register(TypeDef(token="TimeSeries", supertypes=("DataFrame",)))
```

An out-of-core package can ship its own tokens; see `examples/type_plugin_stub/`. An
unregistered token is not an error — `ef.validate` reports it as a non-blocking warning
(`type_unknown`).

Override `infer_types` only when the output type depends on inputs or params. The default
returns each OUT port's declared `data_type`. The signature is:

```python
infer_types(self, node, input_types) -> dict[str, str]
```

Where `input_types` maps IN-port name to its resolved upstream token, and the return maps
OUT-port name to the produced token.

For example, `impute_missing` preserves the table type, so the default is correct and we
override nothing.

> **Note**: Per-dimension tensor shape inference is out of scope here and is roadmap Epic 10;
> structural typing (`Tensor` -> `Tensor`) is all that is resolved.

See [type-system-spec.md](type-system-spec.md) for the full reference.

## Step 7 — Use the derived helpers and test

You get three helpers for free:

```python
defn = ImputeMissing()
node = defn.instantiate(strategy="mean")     # → a graph-valid IR Node
defn.validate_node(node)                     # → [] when valid; error strings otherwise
defn.to_spec()                               # → JSON-able NodeSpec for registry / UI
```

A conformance checklist for your test file:

- `to_spec()` round-trips through JSON;
- `instantiate()` produces a node that fits in a `Graph`;
- `validate_node()` catches a missing required param, a bad `choices` value, and any
  numeric/length/pattern violation;
- `execute` equals running `preview().render()` for a representative node (ADR 0002).

## Registration

Registering the definition so the catalog can discover it (without core changes) is the
**registry / plugin architecture**, Story 4 — it will live alongside `emergentflow/nodes/`. This
guide covers authoring a conforming definition; registration is the next story.
