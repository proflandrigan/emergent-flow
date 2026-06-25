# Package Layout & Namespace Conventions

Package structures and naming conventions for the Emergent Flow SDK.

---

## Install & import

The SDK is distributed as the Python package `emergentflow`. The conventional import alias is:

```python
import emergentflow as ef
```

The `ef` alias is the canonical short form used throughout the ecosystem. The names
`omnicanvas` and `oc` are **not** used and should not appear in code, documentation, or
configuration.

---

## Current package structure

```
emergentflow/
├── __init__.py          (exposes __version__ and core public API)
├── ir/                  (intermediate representation: nodes, ports, edges, graph structure)
│   └── [schema, serialization, validation modules]
├── nodes/               (node contract, registry, and plugin discovery)
│   ├── [contract, registry, spec modules]
│   └── examples/        (reference node implementations)
└── codegen/             (code-generation engine: graph traversal, wiring, compiler/executor)
    └── [traversal, wiring, naming, context, errors, formatting, compiler modules]
```

**`emergentflow.ir`** — the intermediate representation layer. Defines the graph schema: node
and edge definitions, ports, parameters, graph structures, schema versioning, and
serialization/deserialization methods.

**`emergentflow.nodes`** — the node-definition contract, registry, and plugin-discovery system.
All node types (in-tree and third-party) register here. The module exposes a shared
`NodeRegistry` singleton and thin wrappers for lookup and validation.

**`emergentflow.nodes.examples`** — reference implementations of core node types. These nodes
self-register at import time and serve as examples for authoring custom nodes.

**`emergentflow.codegen`** — the code-generation engine (Epic 2). Houses the shared
graph-analysis plumbing that the whole-graph compiler (`ef.compile_to_code`, Story 5) and
the reference executor (`ef.execute`, Story 6) build on. The `ef.compile_to_code(graph) -> str`
entry point is implemented, building on deterministic topological ordering, cycle detection,
and the input-wiring map (Story 2). The `ef.execute(graph) -> results` reference executor is also implemented (Story 6); see [How the codegen executor & equivalence work](codegen-executor.md). The module is exposed as
the lazily-imported `ef.codegen` namespace, so `import emergentflow as ef` stays lightweight and
the package is only pulled in on first access to `ef.codegen`. See
[How codegen traversal works](codegen-traversal.md) and [How codegen compilation works](codegen-compiler.md).
The top-level `ef.compile_to_code` / `ef.execute` entry points are placed per
[ADR 0010](adr/0010-codegen-package-placement.md).

---

## Public namespace convention (functional pipeline)

The following `ef.*` namespaces define the functional-pipeline layer. They are implemented as
of **Epic 1 Story 8** — each is a thin, `@ef.public_op`-decorated wrapper over a trusted
library (see [SDK Design Philosophy](sdk-design-philosophy.md)).

| Namespace | Purpose | Representative call | Backed by |
|-----------|---------|----------------------|-----------|
| `ef.data` | Data ingestion and source loading | `ef.data.load_csv(path)` | pandas |
| `ef.clean` | Cleaning, transformation, and imputation | `ef.clean.impute_missing(df)` | scikit-learn |
| `ef.stats` | Statistical analytics and aggregation | `ef.stats.anova(df, group_col=..., value_col=...)` | statsmodels |
| `ef.ml` | Classical machine learning workflows | `ef.ml.train_classifier(df, target=...)` | scikit-learn |
| `ef.reports` | Automated reporting and visualization | `ef.reports.generate_html_summary(df)` | ydata-profiling |

Each family is registered as a node definition (`data.load_csv`, `clean.impute_missing`,
`stats.anova`, `ml.train_classifier`, `reports.generate_html_summary`) conforming to the Story 3
contract, and a worked end-to-end example lives in
[`examples/vertical_slice/`](../examples/vertical_slice/).

**Note:** the families are imported **lazily** — `import emergentflow as ef` stays lightweight
and the heavy scientific stack is only pulled in the first time you touch `ef.data`, `ef.stats`,
etc. (or import the submodule directly, e.g. `from emergentflow.stats import anova`).

---

## Why a flat verb-namespace layout

The functional-pipeline namespaces (`ef.data`, `ef.clean`, etc.) mirror the node families
advertised in the generated-code example shown in the README. This structure keeps the
canvas-to-code mapping legible: a `data.load_csv` node on the canvas maps directly to a
`ef.data.load_csv()` call in the generated code. The flat verb-based structure maximizes
discoverability — users can type `ef.` and quickly scan all available families.

---

## See also

For naming and return-object rules across the SDK, see
[`docs/public-api-conventions.md`](public-api-conventions.md).
