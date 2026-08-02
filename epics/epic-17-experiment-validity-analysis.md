# Epic 17 — Experiment-Validity Static Analysis

> **Repo numbering.** This is repo **Epic 17** (the next epic delivered in this repo after Epic
> 16), filed from [issue #125](https://github.com/proflandrigan/emergent-flow/issues/125) and
> numbered by repo delivery order per `epics/README.md` (the issue proposed "epic-18" as an
> explicit placeholder). It turns `ef.validate` from *"do these ports fit together?"* into
> *"is this experiment valid?"*.

> The most expensive bugs in applied ML are not crashes, they are silent validity failures: a
> scaler fitted before the split, a feature derived from the target, a random split on temporal
> data, precision@k measured on a shuffle. They produce a model that looks excellent and fails
> in production. They are invisible to types, tests, and code review, and they are exactly what
> a DAG knows. Every one of those failures is a **property of the graph's topology**, which means
> the IR can decide it and a linter over generated Python fundamentally cannot.

**Phase:** Foundation/quality — static, structural checks over the IR. No data inspection, no training run.
**Dependencies:** Epic 3 (validator + `Diagnostic`/`Diagnostics` + rules-as-data), Epic 2 (traversal/wiring), Epics 8/12/15/16 (the node families the rules reason about), issue #113 (`ml.load_model`/`ml.predict`, shipped).
**Blocks / raises the ceiling of:** the agent-experimentation epic (`run_validity_checks` tool), `emergentflow validate --strict` ([#115](https://github.com/proflandrigan/emergent-flow/issues/115)), the PR-review graph-diff bot.
**New hard deps:** none.

---

## Definition of Done (epic-level)

- [x] A versioned validity rule pack, published as data (`schema/validity-rules.json`), with ≥10 rules across leakage, temporal, skew, and metric-appropriateness.
- [x] `ef.validate` runs the pack and returns findings on the existing `Diagnostics` channel, each carrying a `rule_id` and every implicated node (`related_node_ids`).
- [x] Each rule has a documented rationale, a decidability class, a known false-positive shape, and fixture graphs that trip it plus near-miss graphs that must **not** trip it.
- [x] A finding can be suppressed per rule + node (`ef.apply_suppressions`), with the suppression stored beside the graph and visible in the UI (Story 7).
- [x] The canvas explains a finding in plain language and highlights the implicated relationship (Story 7).
- [x] `emergentflow validate --strict` exits non-zero on validity errors (issue #115).
- [x] Zero findings on all bundled example graphs — or, where a demo genuinely trips a rule, the demo is fixed (the epic's own dogfood gate, `tests/test_validity_dogfood.py`).

---

## Stories

### Story 1 — `Diagnostic` gains `rule_id` + `related_node_ids`; schema bumped

Additive, defaulted fields; `schema/diagnostics.schema.json` regenerated; the TS
`Diagnostic` interface updated. **Acceptance:** an older consumer ignoring the new
fields still parses; a finding naming two nodes round-trips.

### Story 2 — Rule registry + rule-pack artifact

A `@validity_rule` registration decorator mirroring the node registry
(`nodes/registry.py`), each rule declaring `id`, `severity`, `confidence`,
`title`, `rationale`, and an `applies_when` gate. Exported as a versioned JSON
artifact (`schema/validity-rules.json`) plus a server route
(`GET /validity-rules`) and the UI build artifact. **Acceptance:**
`ef.build_validity_rules_artifact()` emits the pack; the canvas renders a rule's
rationale without a server call.

### Story 3 — Leakage rules

`fit_before_split` (fitting transform upstream of a split), `target_derived_feature`
(derive_column referencing the target), `global_aggregate_before_split`
(group-by aggregate on the full frame before a split), and (to reach the DoD's
≥10) `global_imputation_before_split` (data-derived imputation before a split).
**Acceptance:** each rule has a tripping fixture and a near-miss fixture (e.g. a
transform fitted on the train output only — must stay silent).

### Story 4 — Temporal rules

`window_crosses_split` (a lag/rolling/ewma window computed across a split
boundary), `random_split_on_temporal_graph` (a shuffled `ml.train_test_split` in
a graph containing timeseries/temporal-recommender nodes). **Acceptance:** as
above, with the near-miss being a correctly ordered per-split window.

### Story 5 — Train/serve skew

`train_serve_skew`: given a scoring path (`ml.load_model` -> `ml.predict`),
diff the transform chain feeding the predict frame against the chain feeding the
supervised training node's frame (both derived from a common fork) and flag
transforms present in one and absent in the other, or applied in a different
order. **Acceptance:** a scoring flow missing one `scale_features` produces a
finding naming the missing node; an equivalent chain produces none.

### Story 6 — Metric-appropriateness rules

`ranking_metrics_on_random_split` (recommend.evaluate downstream of a random
rather than temporal split), `task_mismatched_scoring` (a classification/regression
scoring string applied to the wrong task, decidable from the estimator catalog's
`task` field), `eda_peek_on_test` (auto-EDA/profile on the test frame).
**Acceptance:** each with tripping + near-miss fixtures.

### Story 7 — Canvas surface

Findings appear in the problems list, each row explaining the rule, naming both
implicated nodes, offering *highlight the relationship* and *suppress with a
reason* (suppression stored beside the graph, never on it — ADR 0019).
**Acceptance:** a user with a leakage finding can, without docs, see which two
nodes are at fault and why it matters.

### Story 8 — `docs/experiment-validity-rules.md`

The rule catalog: id, rationale, decidability class, false-positive shape, and
how to suppress. Explicitly disambiguated from `stats.diagnostic_*` model
diagnostics. **Acceptance:** every registered rule appears; a CI check fails if a
rule lacks a doc entry.

---

## Non-goals

- Judging statistical results (effect sizes, p-value correction) — `ef.stats` / `research/quality.py`.
- Data-value validation (nulls, ranges, drift) — `research.assert_data`.
- Any check requiring data inspection or a training run.
- Auto-fixing a finding. Explain, don't rewrite — an auto-fix that moves a transform across a split changes the experiment, which is the human's call.

## Notes / Risks

- **Name collision:** `emergentflow.stats.diagnostics` + `stats/diagnostics_catalog.py` are *model* diagnostics (VIF, normality, heteroscedasticity, autocorrelation). The validity vocabulary ("validity rules" producing validator diagnostics) is deliberately distinct and disambiguated in `docs/experiment-validity-rules.md`.
- **`schema/rules.json` is taken.** It is the type-system rules artifact. The validity pack uses `schema/validity-rules.json`; `ef.build_rules_artifact` (type system) vs `ef.build_validity_rules_artifact` (validity) — never conflate.
- **Topological approximation first.** Story 3's `target_derived_feature` is much stronger with column-level lineage; the topological approximation ships first and is upgraded when the lineage epic lands.
- **Suppression is boundary-side.** `ef.validate` stays a pure function of `(graph, node_registry, type_registry)` (ADR 0002); suppression is a pure filter (`ef.apply_suppressions`) applied by the canvas and CLI.
- **Errors only when certain.** Only decidable-without-inference rules may be `error`; everything else warns, so a false positive never blocks a run.
