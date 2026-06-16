# ADR 0003 — The SDK supports two paradigms from day one

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Colony Mind core team

## Context

The clean example in the Colony Mind proposal — `load_csv(...) → impute_missing(...) → anova(...)` — is a **functional pipeline**: each node is a single function call returning an inspectable object. That shape maps naturally to data engineering, statistics, and classical ML, where work is expressed as a DAG of pure-ish transforms.

It does not, however, map cleanly to two other important workload families:

- **Deep learning.** A neural network is not a sequence of function calls; it is a *declarative module graph* — a class that inherits from `nn.Module`, whose `__init__` wires together child modules and whose `forward` method describes the data path. Forcing this into a function-pipeline shape would produce code that no PyTorch practitioner would recognise or maintain.

- **Multi-agent graphs.** Agent orchestration (e.g. via LangGraph) involves stateful, cyclic-ish control flow — nodes that loop, branch on model output, and pass structured state between steps. This is closer to a compiled graph object than to a linear DAG of transforms.

Designing codegen, execution, and validation around a single paradigm — and discovering the mismatch later — would require a breaking restructure of the IR and the SDK surface at exactly the point where DL and agent workloads are being built.

## Decision

We will design the SDK and codegen around two first-class paradigms from day one:

1. **Functional pipeline** — a DAG of pure-ish transforms, where each node is a function call returning an inspectable result. This paradigm covers data engineering, statistics, classical ML, and reporting. Example:

   ```python
   import colonymind as cm

   graph = (
       cm.load_csv("data/experiment.csv")
         .impute_missing(strategy="median")
         .anova(group_col="treatment", value_col="response")
   )
   result = cm.execute(graph)
   ```

2. **Declarative module/graph definition** — a definition compiled into a class or graph object rather than executed as a chain of calls. This paradigm covers deep learning architectures (via PyTorch `nn.Module`) and agent graphs (via LangGraph). Example:

   ```python
   import colonymind as cm

   classifier = cm.nn_module(
       layers=[
           cm.linear(in_features=128, out_features=64),
           cm.relu(),
           cm.linear(in_features=64, out_features=10),
       ],
       name="SimpleClassifier",
   )
   # compile_to_code emits a proper nn.Module subclass; execute builds the module object
   model = cm.execute(classifier)
   ```

The IR schema must be capable of representing both paradigms. `compile_to_code(ir)` and `execute(ir)` (ADR 0002) must produce correct, idiomatic output for nodes belonging to either paradigm — functional-pipeline nodes emit chained function calls; declarative nodes emit class bodies or graph-construction code.

## Consequences

**Positive:**

- Codegen for DL and agent workloads produces idiomatic Python from day one — a `nn.Module` subclass, not a disguised function chain — preserving the "glass-box" promise where it matters most.
- The IR and execution engine are architected to handle both paradigms before the pressure of Phase 3 DL/agent work; there is no late-stage structural rewrite.
- Node-family authors have a clear contract: declare which paradigm a node belongs to, and the codegen and execution machinery handles the rest.

**Negative / obligations:**

- The IR schema (Epic 1, Story 2) must model both paradigms now, even though DL node families and agent node families do not arrive until Phase 3. This is a modest up-front cost in IR design that prevents a much larger cost later.
- `compile_to_code` and `execute` must branch on paradigm; the equivalence invariant from ADR 0002 must hold independently for each paradigm. The golden-test corpus must include representative graphs from both shapes.
- Pretending everything is a function call — and deferring the second paradigm — would produce ugly, non-idiomatic DL and agent code at exactly the point the proposal promises clean output.

**Deferred:**

- The concrete DL node family (`nn.Module`-backed nodes) and the agent node family (LangGraph-backed nodes) are deferred to Phase 3. The IR and SDK *plumbing* for the declarative paradigm is designed now; the node implementations arrive later.
