# Package Layout & Namespace Conventions

Package structures and naming conventions for the Colony Mind SDK.

---

## Install & import

The SDK is distributed as the Python package `colonymind`. The conventional import alias is:

```python
import colonymind as cm
```

The `cm` alias is the canonical short form used throughout the ecosystem. The names
`omnicanvas` and `oc` are **not** used and should not appear in code, documentation, or
configuration.

---

## Current package structure

```
colonymind/
├── __init__.py          (exposes __version__ and core public API)
├── ir/                  (intermediate representation: nodes, ports, edges, graph structure)
│   └── [schema, serialization, validation modules]
└── nodes/               (node contract, registry, and plugin discovery)
    ├── [contract, registry, spec modules]
    └── examples/        (reference node implementations)
```

**`colonymind.ir`** — the intermediate representation layer. Defines the graph schema: node
and edge definitions, ports, parameters, graph structures, schema versioning, and
serialization/deserialization methods.

**`colonymind.nodes`** — the node-definition contract, registry, and plugin-discovery system.
All node types (in-tree and third-party) register here. The module exposes a shared
`NodeRegistry` singleton and thin wrappers for lookup and validation.

**`colonymind.nodes.examples`** — reference implementations of core node types. These nodes
self-register at import time and serve as examples for authoring custom nodes.

---

## Public namespace convention (functional pipeline)

The following `cm.*` namespaces define the functional-pipeline layer. They are a **documented
convention**; the node families implementing these operations land in **Epic 1 Story 8** and
are not yet importable.

| Namespace | Purpose | Representative call |
|-----------|---------|----------------------|
| `cm.data` | Data ingestion and source loading | `cm.data.load_csv(path)` |
| `cm.clean` | Cleaning, transformation, and imputation | `cm.clean.impute_missing(table)` |
| `cm.stats` | Statistical analytics and aggregation | `cm.stats.anova(groups)` |
| `cm.ml` | Classical machine learning workflows | `cm.ml.train_classifier(X, y)` |
| `cm.reports` | Automated reporting and visualization | `cm.reports.generate_html_summary(data)` |

**Important:** these namespaces are a documented convention describing the planned structure
and API surface. The node implementations and Python functions are **not yet available for
import**. They will be added as part of Epic 1 Story 8.

---

## Why a flat verb-namespace layout

The functional-pipeline namespaces (`cm.data`, `cm.clean`, etc.) mirror the node families
advertised in the generated-code example shown in the README. This structure keeps the
canvas-to-code mapping legible: a `data.load_csv` node on the canvas maps directly to a
`cm.data.load_csv()` call in the generated code. The flat verb-based structure maximizes
discoverability — users can type `cm.` and quickly scan all available families.

---

## See also

For naming and return-object rules across the SDK, see
[`docs/public-api-conventions.md`](public-api-conventions.md).
