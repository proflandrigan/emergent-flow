# Node Registry and Plugin Discovery

The registry is the indexed catalog of every node type Colony Mind knows about. It bridges
the gap between a fixed tool (a monolith where every node is hardcoded) and a platform (a
system where new node types are added declaratively and the catalog grows without touching
core). The catalog can expand via two paths: in-tree definitions that self-register at
import time, and out-of-core plugins distributed as separate Python packages.

For the contract a node must satisfy before it can be registered, see
[`node-contract-spec.md`](node-contract-spec.md) and
[ADR 0005](adr/0005-node-definition-contract.md). For the architectural rationale behind the
registry and plugin model, see [ADR 0006](adr/0006-node-registry-and-plugin-discovery.md).

---

## What the registry is

`colonymind.nodes.NodeRegistry` is an indexed catalog of `NodeDefinition` subclasses, keyed
by their `type` string (e.g. `"data.load_csv"`). That key equals `NodeSpec.type` and
`Node.type` — it is the single thread tying the catalog entry to every IR instance of that
type.

The module exposes a default singleton:

```python
from colonymind.nodes import registry        # the shared NodeRegistry instance
```

Most code targets this singleton through the thin module-level wrappers (`register`, `get`,
`by_family`, `by_port_type`, `validate`, `discover`). Tests that need isolation create a
fresh `NodeRegistry()` instead.

---

## Two registration paths

### In-tree: `@register` decorator

In-tree node definitions (those shipped as part of `colonymind`) use the `@register`
decorator, which registers the class in the default singleton immediately at import time:

```python
from colonymind.nodes.contract import NodeDefinition
from colonymind.nodes.registry import register

@register
class LoadCsv(NodeDefinition):
    type   = "data.load_csv"
    family = "data"
    label  = "Load CSV"
    ...
```

Registration fires when the module is imported. Importing `colonymind.nodes` pulls in
the reference-node package for you, so the default `registry` is populated with both
reference nodes (`data.load_csv` and `clean.impute_missing`) on first import:

```python
from colonymind.nodes import registry   # importing the package registers the in-tree nodes

assert "data.load_csv" in registry
assert "clean.impute_missing" in registry
```

The reference implementations live in `colonymind/nodes/examples/`.

### Out-of-core: entry points + `discover()`

A third-party package (or any package outside `colonymind`) contributes nodes by declaring
an entry point in the `colonymind.nodes` group. No fork of core is required.

In the plugin's `pyproject.toml`:

```toml
[project.entry-points."colonymind.nodes"]
text_reverse = "cm_texttools.nodes:ReverseText"
```

Each value is a dotted import path to a `NodeDefinition` subclass. The key (`text_reverse`)
is an arbitrary entry-point name — the catalog key comes from the class's `type` attribute,
not from the entry-point name.

The plugin class itself does **not** call `@register`; registration is handled by
`discover()` when the host application loads plugins:

```python
from colonymind.nodes import discover

problems = discover()      # scans "colonymind.nodes" entry points
if problems:
    for p in problems:
        print("plugin warning:", p)
```

The worked example is `examples/plugin_stub/` (package `cm-texttools`, node `text.reverse`).
Install it with `pip install -e examples/plugin_stub/` and then call `discover()` to add
`text.reverse` to the default registry.

---

## Lookup APIs

All lookups return definition *classes*, not instances. Call `.to_spec()` on an instance to
get the JSON-serializable `NodeSpec`; the `specs()` method does that in bulk for the entire
catalog.

### `get(type_key) -> type[NodeDefinition]`

Raises `KeyError` if absent.

```python
from colonymind.nodes import get

LoadCsv = get("data.load_csv")
spec = LoadCsv().to_spec()
```

### `try_get(type_key) -> type[NodeDefinition] | None`

Non-raising variant; returns `None` if the key is not registered.

```python
from colonymind.nodes import registry

defn = registry.try_get("data.load_csv")
if defn is not None:
    node = defn().instantiate(path="data.csv")
```

### `by_family(family) -> list[type[NodeDefinition]]`

Returns all definitions whose `family` equals the argument, sorted by `type`.

```python
from colonymind.nodes import by_family

data_nodes = by_family("data")      # [LoadCsv, ...]
```

### `by_port_type(data_type, direction=None) -> list[type[NodeDefinition]]`

Returns all definitions declaring at least one port with the given `data_type` token.
`direction` is a `colonymind.ir.common.Direction` (`Direction.IN` or `Direction.OUT`), or
`None` to match ports of either direction. Results are sorted by `type`.

```python
from colonymind.nodes import by_port_type
from colonymind.ir.common import Direction

consumers = by_port_type("Table", direction=Direction.IN)
producers = by_port_type("Table", direction=Direction.OUT)
either    = by_port_type("Table")
```

Note: `data_type` matching is an opaque token comparison today. Real type-system-aware
matching (structural subtyping) is deferred to Epic 5.

### `all() -> list[type[NodeDefinition]]`

Returns every registered definition, sorted by `type`.

```python
from colonymind.nodes import registry

for defn in registry.all():
    print(defn.type, defn.label)
```

`registry` also supports direct iteration (`for defn in registry`) and `len(registry)`.

### `specs() -> list[NodeSpec]`

Returns a serializable catalog view — one `NodeSpec` per registered definition, sorted by
`type`. This is the payload the UI fetches to populate its node palette; it contains no
Python behavior.

```python
from colonymind.nodes import registry
import json

catalog_json = json.dumps([s.model_dump() for s in registry.specs()])
```

### `in` operator

```python
from colonymind.nodes import registry

if "data.load_csv" in registry:
    ...
```

---

## Validation

Two independent validation layers exist; they serve different purposes.

### Per-definition: `register()` fail-fast checks

`register()` (and the `@register` decorator) runs these checks synchronously and raises
`ValueError` on the first violation:

1. The argument must be a proper `NodeDefinition` subclass (not the abstract base itself,
   not a non-class object).
2. `type`, `family`, and `label` must be present, non-empty strings.
3. `definition().to_spec()` must succeed (proves the definition is concrete and well-formed,
   and that Pydantic validates the full `NodeSpec`).
4. Registering a *different* class under an already-registered `type` key raises
   `ValueError`. Registering the *same* class object again is a harmless no-op.

Because registration fires at import time (for `@register`-decorated classes), a broken node
module raises on import rather than silently polluting the catalog.

### Whole-catalog: `validate() -> list[str]`

`validate()` sweeps every registered definition and returns human-readable problem messages
(never raises, never modifies the registry). Use it in CI startup checks:

```python
from colonymind.nodes import validate

problems = validate()
assert not problems, "\n".join(problems)
```

Checks performed per definition:

- Stored key matches `definition.type` (guards against direct `_defs` manipulation).
- `definition().to_spec()` succeeds (re-validates after any post-registration mutation).
- Port name uniqueness per direction (duplicate IN/IN or OUT/OUT names).
- Param name uniqueness.
- `version` is an `int >= 1`.

---

## Discovery

`discover(*, group="colonymind.nodes") -> list[str]` scans all installed packages for entry
points in `group`, loads each one, and passes the result to `register()`.

```python
from colonymind.nodes import discover, ENTRY_POINT_GROUP

print("scanning group:", ENTRY_POINT_GROUP)   # "colonymind.nodes"
problems = discover()
```

The constant `ENTRY_POINT_GROUP = "colonymind.nodes"` is the canonical group name; override
`group` only in tests or when running a custom plugin marketplace.

**Resilience contract:** a single misbehaving entry point — `load()` raises, the loaded
object is not a valid `NodeDefinition` subclass, or `register()` rejects it — does not abort
discovery of the remaining entry points. Each failure is appended to the returned list;
successful entries still register. The return value is empty when every entry point processed
cleanly.

Calling `discover()` when some plugins are already registered is safe: `register()` is
idempotent for the same class object, and a conflicting duplicate becomes a recorded problem
rather than a raised exception.

---

## Quickstart

### Register a node (in-tree)

```python
from colonymind.nodes.contract import NodeDefinition, CodeFragment
from colonymind.nodes.registry import register
from colonymind.nodes.spec import PortSpec, ParamSpec
from colonymind.ir.common import Direction

@register
class Normalize(NodeDefinition):
    type   = "clean.normalize"
    version = 1
    family = "clean"
    label  = "Normalize"

    ports = [
        PortSpec(name="table", direction=Direction.IN,  data_type="Table"),
        PortSpec(name="table", direction=Direction.OUT, data_type="Table"),
    ]
    params = [
        ParamSpec(name="method", type_token="str", default="z-score"),
    ]

    def execute(self, node, inputs):
        ...

    def codegen(self, node):
        return CodeFragment(
            imports=["from colonymind.nodes.examples.normalize import normalize"],
            body="table = normalize(table)",
        )
```

### Ship a plugin (out-of-core)

1. Create a package with a `NodeDefinition` subclass (do **not** call `@register`; the entry
   point handles registration).

2. Declare the entry point in `pyproject.toml`:

   ```toml
   [project.entry-points."colonymind.nodes"]
   my_node = "mypackage.nodes:MyNodeClass"
   ```

3. Install the package (`pip install -e .` during development).

4. Call `discover()` once at startup (or in your test setup):

   ```python
   problems = discover()
   assert not problems
   ```

See `examples/plugin_stub/` for a complete, minimal example (`cm-texttools`, node
`text.reverse`).
