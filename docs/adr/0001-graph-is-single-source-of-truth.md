# ADR 0001 — Graph is the single source of truth; code is a compiled artifact

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Colony Mind core team

## Context

Colony Mind promises both a visual canvas for building pipelines and clean, exportable Python
that users can push to Git. These two representations create a tempting symmetry: what the
user draws on the canvas becomes runnable code, and ideally any edits to that code would
reflect back on the canvas.

The trap in that symmetry is bidirectional sync. Making edits to exported `.py` files flow
back to the canvas would require parsing arbitrary, potentially hand-edited Python back into
a node graph via AST analysis. This is an enormous, fragile, and low-ROI undertaking — the
surface area of Python that must be correctly parsed and mapped to graph nodes is unbounded,
and any deviation from the generated style breaks the round-trip.

Treating the canvas and the generated code as two co-equal representations that must stay in
sync is therefore not viable early in the platform's life. A clear ownership hierarchy is
needed.

## Decision

We will treat the serialized graph (the Intermediate Representation defined in Epic 1) as
the single canonical source of truth for a pipeline. Generated Python is a one-way build
output, analogous to compiled assembly — it faithfully represents the graph at the moment of
export but is not an authoritative representation of pipeline intent. Git export is a publish
step, not a sync: pushing code to a repository is a snapshot, not a live mirror. We will
defer any Python-to-graph parser; reverse round-tripping may be revisited later as a
contained, opt-in feature but will not gate the platform.

## Consequences

**Positive:**

- Preserves the "glass-box" promise: users can always see and run the exact generated code
  without Colony Mind owning a Python decompiler.
- Dramatically narrows scope for Epic 1: the IR is the only format that must be kept
  consistent; code generation is a one-directional transform.
- Eliminates an entire class of hard-to-diagnose sync bugs where canvas state and file state
  diverge.

**Negative / user-facing:**

- Edits made directly to exported `.py` files in Git do **not** flow back to the canvas.
  This is a user-facing consequence that must be clearly communicated in documentation and
  the UI (e.g. a banner or comment in generated files stating they are auto-generated and
  edits will be overwritten on the next export).

**Deferred:**

- Reverse round-tripping (Python → graph) is explicitly out of scope for the current
  platform phase. It can be revisited as a contained, opt-in feature once the core IR and
  code-generation path are stable.
