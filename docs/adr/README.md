# Architecture Decision Records

This directory records the significant architectural decisions for Colony Mind, using a
lightweight [MADR](https://adr.github.io/madr/)-style format (Status · Context · Decision ·
Consequences). See [`TEMPLATE.md`](./TEMPLATE.md) to author a new one.

The four foundational decisions below are upstream of the IR schema and nearly every epic;
they correspond to §A of the [technical roadmap](../../planning_docs/technical_roadmap.md)
and Story 1 of [Epic 1](../../epics/epic-1-core-sdk-and-ir.md).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0001](./0001-graph-is-single-source-of-truth.md) | Graph is the single source of truth; code is a compiled artifact | Accepted |
| [0002](./0002-execute-the-ir-not-the-string.md) | Execute the IR, not the generated string | Accepted |
| [0003](./0003-sdk-supports-two-paradigms.md) | The SDK supports two paradigms from day one | Accepted |
| [0004](./0004-storage-tiering.md) | Storage tiering: metadata in Redis, artifacts on disk/object store | Accepted |
| [0005](./0005-node-definition-contract.md) | Node-definition contract: a serializable spec plus Python behaviour | Accepted |

The following decisions lock the codegen engine's architecture; they correspond to Story 1 of
[Epic 2](../../epics/epic-2-code-generation-engine.md).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0008](./0008-codegen-templating-vs-ast.md) | Codegen: string templates for functional pipelines, AST construction for the declarative paradigm | Accepted |
| [0009](./0009-codegen-binding-context.md) | The whole-graph compiler supplies variable names to nodes via a `CodegenContext` | Accepted |
| [0010](./0010-codegen-package-placement.md) | The codegen engine lives in `colonymind/codegen` with `cm.compile_to_code` / `cm.execute` entry points | Accepted |

The following decisions lock the type system's architecture; they correspond to Story 1 of
[Epic 3](../../epics/epic-3-type-safe-graph-and-validation.md).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0011](./0011-type-model-and-compatibility.md) | Nominal type model with an optional subtype relation and three-valued compatibility | Accepted |
| [0012](./0012-rules-as-portable-data.md) | Ship the type rules as versioned data, with the SDK as authoritative re-validator | Accepted |

## Conventions

- Filenames: `NNNN-kebab-case-title.md`, numbered sequentially from `0001`.
- One decision per record. Once **Accepted**, an ADR is immutable — supersede it with a new
  ADR rather than editing the decision.
