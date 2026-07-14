# Architecture Decision Records

This directory records the significant architectural decisions for Emergent Flow, using a
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
| [0010](./0010-codegen-package-placement.md) | The codegen engine lives in `emergentflow/codegen` with `ef.compile_to_code` / `ef.execute` entry points | Accepted |

The following decisions lock the type system's architecture; they correspond to Story 1 of
[Epic 3](../../epics/epic-3-type-safe-graph-and-validation.md).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0011](./0011-type-model-and-compatibility.md) | Nominal type model with an optional subtype relation and three-valued compatibility | Accepted |
| [0012](./0012-rules-as-portable-data.md) | Ship the type rules as versioned data, with the SDK as authoritative re-validator | Accepted |

The following decision revisits the repo/packaging topology set out in §A5 of the
[technical roadmap](../../planning_docs/technical_roadmap.md).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0013](./0013-single-repo-bundled-ui-topology.md) | Single repo, single package: bundle the canvas UI with the SDK (JupyterLab model), preserving the coupling invariant | Accepted |

The following decision reconciles non-deterministic LLM/network nodes with the ADR-0002 purity/
equivalence invariant; it governs [Epic 9](../../epics/epic-9-ai-engineering-playground-prompt-lab.md)
(the Prompt Lab / AI-engineering-playground wedge) and the GenAI/agent epics that follow.

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0017](./0017-llm-nodes-injected-effectful-client.md) | LLM/network nodes call an injected `LLMClient` seam; the effect lives at the edge, so the pure core and the equivalence gate stay intact | Accepted |

The following decision generalizes ADR 0017's injected-client seam to a second effect type (data-source
connectors) and fixes the secret-free connection-reference boundary; it governs
[Epic 13](../../epics/epic-13-data-connectors-warehouses-sql.md) (Data Connectors, Warehouses & SQL).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0018](./0018-data-source-connector-seam.md) | Data-source connectors are a second injected effectful-client seam (`WarehouseClient`), resolved through one extensible client bundle; connection references in the IR stay secret-free | Accepted |

The following decision introduces graph sessions and agent collaboration — the first stateful
server surface — and records the works-without-agents invariant that governs
[Epic 14](../../epics/epic-14-agent-collaboration.md) (Agent Collaboration on the Canvas).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0019](./0019-graph-sessions-and-agent-collaboration.md) | Graph sessions and agent collaboration: stateful sessions beside a stateless IR; collaboration state never on the `Graph`; optimistic concurrency; HTTP-first agent surface; gate policy at the routes; works-without-agents enforced by regression suite | Accepted |

The following decision introduces SHAP-based explainability and error analysis as a new `explain`
family; it governs Epic 11 (Model Explainability).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0020](./0020-model-explainability-family.md) | SHAP-based explainability and error analysis is a new `explain` family, a pure allow-listed reader of `ml.FittedModel` | Accepted |

The following decision locks the recommender-systems architecture — archetypes, representations,
and the optional-extra boundary; it governs [Epic 15](../../epics/epic-15-recommender-systems.md)
(Recommender Systems).

| ADR | Decision | Status |
| :-- | :------- | :----- |
| [0021](./0021-recommender-systems-architecture.md) | Recommender systems are a parallel `recommend` family with their own archetypes, representations, and optional-extra boundary — not an extension of the sklearn estimator adapter | Accepted |

## Conventions

- Filenames: `NNNN-kebab-case-title.md`, numbered sequentially from `0001`.
- One decision per record. Once **Accepted**, an ADR is immutable — supersede it with a new
  ADR rather than editing the decision.
