# Epic 18 — Column-Level Lineage

> **Repo numbering.** This is repo **Epic 18** (the next epic delivered in this repo after Epic
> 17), filed from [issue #128](https://github.com/proflandrigan/emergent-flow/issues/128) and
> numbered by repo delivery order per `epics/README.md` (the issue proposed "epic-21" as an
> explicit placeholder). It upgrades lineage from *"which nodes fed this node"* to
> *"where did this column come from"*.

> **The thesis.** *"Click this column and show me every transform that produced it"* is the one
> capability dbt users pay real money for and ML engineers simply do not have — their features are
> assembled across notebook cells and helper modules with no provenance at all. EF is structurally
> able to answer it, because the pipeline is a typed DAG rather than a pile of scripts. This is
> also the epic that upgrades target-leakage detection from a topological approximation to an exact
> answer.

**Phase:** Foundation/quality — column semantics declared on the node contract, extended lineage
traversal over the IR, runtime schema refinement. No new hard deps.
**Dependencies:** Epic 1 (node contract/spec — extended), Epic 16 (`research/lineage.py`,
`data_dictionary` — extended), #105's `ArtifactStore` (observed schemas for runtime refinement),
issue #113 (`ml.load_model`/`ml.predict`, shipped).
**Blocks / raises the ceiling of:** the validity epic's `target_derived_feature` rule (exact rather
than approximate), feature documentation/hand-off generally, and any future feature-store or
data-contract story.
**New hard deps:** none.

---

## Why this epic

Lineage today is **node-level**. `emergentflow/research/lineage.py` defines `LineageNode`
(`node_id`, `node_type`, `label`) and `LineageEdge` (`source_node_id`, `source_port`,
`target_node_id`, `target_port`), with `trace_lineage(graph, node_id)` computed as a pure on-demand
function, surfaced via `POST /lineage` and `ui/src/inspector/LineagePanel.tsx`.

That answers *"which nodes fed this node"*. It does not answer any of the questions an engineer
actually asks:

- *Where did `user_tenure_days` come from?*
- *Is `revenue_bucket` derived from the target I'm predicting?* (the exact leakage question)
- *If the upstream source drops `signup_ts`, what breaks?*
- *Which of my 84 features actually trace back to the events table versus the profile table?*

The raw material is present and unexploited. Every executed table payload already carries
`columns` and `dtypes` (`server/payload.py`). `clean/expressions.py` already parses and validates
the column references inside a `derive_column` expression. `select_columns`, `merge`, `semi_join`,
`reshape`, `group_by_aggregate`, `encode_categorical`, and `explode_lists` are all *declarative
about columns* — their params name them. `stats.data_dictionary` already profiles a frame's
columns. Nothing joins these into a chain.

**This is the most expensive epic delivered so far**, and worth saying so plainly: column semantics
have to be declared for ~138 nodes. The mitigation is that the long tail is trivial — most nodes
are row-wise passthrough — and the declaration is per-node metadata, so it can land incrementally
with an explicit "unknown" state rather than a big-bang migration.

## Structural bets (each mirrors an existing precedent)

1. **Lineage stays a pure function of the graph, never a stored field.**
   `research/lineage.py` already argues this: adding a field would force a schema bump and make two
   structurally identical graphs serialize differently. Column lineage extends the same on-demand
   computation.
2. **Column behaviour is declared on the node contract, like ports and params.** A new optional
   `column_effect` on the node spec (`nodes/spec.py`, `nodes/contract.py`) — the same
   declare-then-generate pattern the catalog already uses, so the canvas gets it as data with no
   new plumbing.
3. **Static first, runtime refinement second.** Many nodes are statically decidable
   (`select_columns` names its columns). Some are not (`data.sql_query`'s output depends on the
   warehouse; `custom_code` is arbitrary). Those resolve from the last run's observed
   `columns`/`dtypes`, which `ArtifactStore` (#105) already persists per node.
4. **"Unknown" is a first-class answer.** A chain that passes through `script.custom_code` must
   report *"provenance breaks here"* rather than guessing. A lineage tool that quietly invents
   edges is worse than none.
5. **The inverse query is half the value.** Impact analysis ("what depends on this column") is the
   maintenance question, and it is the same graph walked backwards.

**Lives in:** `emergentflow/research/lineage.py` (the column model + traversal),
`emergentflow/nodes/` (the `column_effect` declaration + per-node declarations),
`emergentflow/server/` (a column-scoped lineage route), `ui/src/inspector/` (LineagePanel +
clickable columns in `PayloadView`), `docs/`.

> **Deliberate scope boundary.** Column lineage is **provenance**, not data quality: it says where
> a column came from, not whether its values are good (`research.assert_data`). It also stops at
> the graph boundary — tracing into a warehouse's upstream tables is a warehouse-catalog concern,
> though the `sql_query` node should record the source relations it read so the chain can be
> handed off cleanly.

---

## Definition of Done (epic-level)

- [ ] `trace_column_lineage(graph, node_id, column)` returns the full derivation chain for one
      column, with an explicit `unknown` boundary wherever provenance genuinely breaks.
- [ ] Node specs can declare a `column_effect`; the declaration is exported in the catalog so the
      canvas consumes it as data.
- [ ] ≥80% of registered nodes declare their column effect; the remainder report `unknown`
      explicitly, and a CI report lists which nodes are still undeclared.
- [ ] Statically undecidable nodes refine from the last observed run schema.
- [ ] Clicking a column in a result table highlights its contributing upstream path on the canvas
      and shows the derivation trail in the inspector.
- [ ] Impact analysis: given a source column, list every downstream column and node that depends
      on it.
- [ ] The validity epic's `target_derived_feature` rule is rewritten on top of column lineage, with
      a fixture proving it catches a two-hop derivation the topological version misses.

---

## Stories

### Story 1 — Column lineage model
`ColumnLineageNode` (node id + column name + role: source / passthrough / renamed / derived /
aggregated / encoded / dropped / unknown) and `ColumnLineageEdge`, extending `Lineage` without
touching the `Graph` schema. Serializable, inspectable, cycle-safe.
**Acceptance:** the model round-trips as JSON; a chain crossing a rename and a derivation is
represented exactly.

### Story 2 — `column_effect` on the node contract
An optional declaration on `NodeSpec`: which input columns map to which output columns, and how.
Exported in the catalog artifact. Absent declaration ⇒ `unknown`, not a guess.
**Acceptance:** the contract is documented in `docs/authoring-a-node.md` and
`docs/node-contract-spec.md`; the catalog export includes it; an undeclared node yields an
`unknown` boundary rather than a silent passthrough assumption.

### Story 3 — Declare the high-value families
`clean.*` first (`select_columns`, `merge`, `semi_join`, `reshape`, `derive_column` — reusing the
existing expression parser for its exact input columns, `deduplicate`, `explode_lists`,
`encode_lists`, `cast_types`, `parse_dates`, `clean_text`, `redact_pii`), then `transform.*`
(`scale_features`, `encode_categorical` with its expansion fan-out, `discretize`,
`generate_features`), then `stats.group_by_aggregate` and the `data.load_*` sources.
**Acceptance:** a realistic 15-node cleaning + feature flow traces end to end with no `unknown`
boundary.

### Story 4 — Runtime refinement
For `sql_query` / `query_builder` / `http_fetch` / `custom_code`, resolve the output column set
from the last run's observed schema via `ArtifactStore`, marked as *observed* rather than
*declared* so a user can tell the difference.
**Acceptance:** a `sql_query`-rooted flow traces after one run; before any run it reports
`unknown` honestly; `custom_code` always terminates the chain with a stated break.

### Story 5 — `POST /lineage/column` + inspector UX
Column-scoped route; `PayloadView`'s table headers become clickable; the canvas highlights the
contributing path; `LineagePanel` renders the derivation trail as readable steps ("`revenue` →
`log1p` → `revenue_log`") rather than a node list.
**Acceptance:** clicking a column in a run's output table shows its provenance without a page
reload, and dims non-contributing nodes on the canvas.

### Story 6 — Impact analysis (the inverse)
`trace_column_impact(graph, node_id, column)` — everything downstream that consumes it. Surfaced as
"what breaks if this goes away", including a warning when the answer includes an `unknown`
boundary (i.e. the true blast radius may be larger).
**Acceptance:** removing a source column is previewable before it is done; the answer is honest
about unknown regions.

### Story 7 — Rewrite `target_derived_feature` on column lineage
Replace the validity epic's topological approximation with an exact check: does the target column
appear anywhere in the provenance of a feature column.
**Acceptance:** a two-hop leak (target → intermediate → feature) is caught; a legitimate use of the
target as the label only is not flagged.

### Story 8 — Undeclared-node report
A CI-visible report of nodes lacking a `column_effect`, so coverage is tracked rather than
asserted, and adding a node can't silently regress lineage quality.
**Acceptance:** the report lists undeclared nodes with their families; the number is visible in CI
output.

---

## Non-goals

- Column-level *data quality* (`research.assert_data`) or drift.
- Tracing into warehouse upstreams beyond recording the relations `sql_query` read.
- Inferring provenance through `custom_code` by parsing user Python — the chain breaks there and
  says so.
- Storing lineage on the `Graph` (explicitly rejected by the existing `lineage.py` contract).
