# ADR 0016 — Lock the scikit-learn estimator-adapter architecture

- **Status:** Proposed
- **Date:** 2026-07-01
- **Deciders:** Emergent Flow core team

## Context

Repo Epic 6 Story 6 shipped a demo-sized `ef.ml` slice (`train_test_split`, `train_regressor`,
`train_random_forest`, `predict`, `evaluate` in `emergentflow/ml/__init__.py`) that proves the
`FittedModel` representation and the `Model` type token by construction, on a handful of
hand-written estimators. Repo Epic 8 (roadmap Epic 4's deferred "full estimator catalog") must
scale that slice to essentially every scikit-learn estimator that exposes the standard `fit` +
(`predict` | `transform` | `fit_predict` | `score_samples`) protocol — on the order of 200
estimators across classification, regression, clustering, decomposition, manifold, mixture,
preprocessing, feature selection, and outlier/novelty detection.

The Epic 6 precedent — one `NodeDefinition` file per estimator, each with its own
[ADR 0002](./0002-execute-the-ir-not-the-string.md) equivalence test — does not scale to that
breadth: it would mean ~200 hand-maintained node files and ~200 bespoke equivalence tests,
turning "complete sklearn support" into a permanent maintenance sink rather than a one-time
build. Unlike every prior epic (which ships the smallest useful node set and treats the catalog
as intentionally unbounded), scikit-learn is the deliberate exception where completeness is the
point — users expect "if it's in sklearn, it's a node." That reversal only works if breadth is
delivered as curated *data* consumed by a handful of generic node *archetypes*, not as N
individually authored files.

This ADR locks the architecture before any building starts: whether identity/breadth is a
generic adapter or per-node files, whether estimator identity is a node `type` or a `param`, the
fixed port shapes for each archetype, the codegen readability policy, the catalog curation
policy, and the param-surface policy. These are cheap to decide now and expensive to retrofit
once dozens of generated nodes, a canvas palette, and an equivalence-test matrix depend on them.

## Decision

**1. Adapter over per-node files.** We will deliver estimator breadth through a **single
generic adapter** (`ef.ml.fit_estimator` for the fit/fit_transform/cluster archetypes,
`ef.ml.apply_estimator` for predict/transform/score) plus a **small, fixed set of archetype
node types**, with the actual ~200-estimator catalog generated as data rather than hand-written
as code. We will **not** author one `NodeDefinition` subclass per sklearn estimator.

The trade-off is uniformity versus bespoke ergonomics. A per-node-file approach gives each
estimator its own hand-tuned `codegen`/`execute` pair and lets [ADR 0002](./0002-execute-the-ir-not-the-string.md)
equivalence be proven — and broken — independently per estimator; at ~200 estimators that is
~200 places for the codegen/execute pair to drift apart, and ~200 [ADR 0005](./0005-node-definition-contract.md)
contracts to keep in sync by hand. Routing every archetype through one adapter wrapper instead
means `codegen` and `execute` call the identical `ef.ml.*` function for every estimator in the
catalog, so ADR-0002 equivalence holds **by construction across the whole catalog** the moment
it holds for the adapter itself — the same trick the Epic 1 reference nodes used once, applied
once here instead of N times. The cost is that no individual estimator gets bespoke codegen
polish or a hand-tuned node contract; we accept that cost because at this scale uniformity is
what keeps the catalog tractable and the equivalence gate meaningful, and because it turns
"add an estimator" into a reviewed data change (an allow-list entry) rather than a new Python
file with its own test suite.

**2. Estimator identity is a param, not a node type.** A node's `type` captures its archetype
— the shape of the sklearn protocol it wraps — rather than the specific estimator class. The
four archetypes (`ml.fit_estimator`, `ml.fit_transform`, `ml.cluster_detect`,
`ml.apply_estimator`) form a tiny, fixed set enumerated in subsection 3 below. *Which* sklearn
class gets fit at runtime (e.g. `"RandomForestClassifier"`, `"KMeans"`, `"StandardScaler"`) is
expressed as a validated string parameter named `estimator` on that node, resolved through a
curated allow-list registry that maps each estimator key to its import path and accepted
keyword arguments.

The alternative — encoding estimator identity as the node type, e.g. a distinct
`ml.random_forest_classifier` node type per estimator — was rejected because it would
reintroduce the ~200-node-type sprawl that subsection 1 already decided against, and it
complicates the canvas palette schema instead of simplifying it: every new estimator would
require a new type constant and palette entry, inflating the schema in lockstep with the
catalog rather than keeping it fixed across the four archetypes. A param-based design keeps
the node `type` enum bounded and stable while letting the catalog grow as data — adding a new
scikit-learn class means adding one entry to the allow-list, not authoring a new
`NodeDefinition` subclass with its own codegen and equivalence test. That is the same
"reviewed data change" pattern that subsection 1 commits to.

**3. The four archetypes.** The port shape of every generated estimator node is fixed here so
that adapter codegen and canvas edge-validation know exactly what edges each node type accepts:

- **`ml.fit_estimator` (fit, supervised):** `DataFrame` (+ a `target` param) → `Model` —
  covers classifiers and regressors.
- **`ml.fit_transform` (unsupervised transformer):** `DataFrame` → `Transformer` + `DataFrame`
  — covers scalers, encoders, PCA/decomposition, manifold, feature selection.
- **`ml.cluster_detect` (unsupervised label/score):** `DataFrame` → `Model` + `DataFrame` (with
  an added `cluster` or `anomaly_score` column) — covers KMeans/DBSCAN/GMM,
  IsolationForest/LocalOutlierFactor.
- **`ml.apply_estimator` (apply):** consumes a fitted `Model` or `Transformer` + a `DataFrame`
  and covers `predict` / `transform` / `evaluate`.

These four are fixed now because widening or splitting an archetype after the catalog is
generated means re-touching every already-generated node's port wiring and every canvas
edge-validation rule (Epic 3 type-compatibility rules for `Model`/`Transformer` ports) — so
getting the shape right here, before Story 2 builds the adapter and Story 7 generates the
catalog, is exactly the "cheap to decide, expensive to retrofit" case the epic file calls out.

**4. Codegen readability policy.** The default (and only thing built in this epic) is that
codegen emits calls to the adapter itself — e.g. `ef.ml.fit_estimator(frame,
estimator="RandomForestClassifier", target="y", params={...})` — rather than the native
sklearn call (e.g. `sklearn.ensemble.RandomForestClassifier(...)`). This is what makes
[ADR 0002](./0002-execute-the-ir-not-the-string.md) equivalence-by-construction hold:
`codegen` and `execute` invoke the literal same Python function, so there is nothing
per-estimator left to prove equivalent.

"Transparent codegen" — emitting the native `sklearn.*(...)` call directly for prettier,
more idiomatic generated scripts — is a deferred enhancement, not ruled out forever. It is
deferred rather than built now because it would require its own per-estimator equivalence
proof (defeating the whole point of subsection 1's "prove it once" adapter strategy) and is
a pure readability/ergonomics improvement with no capability gain, so it does not earn its
cost until there is demand for prettier exported scripts.

**5. Curation policy.** The catalog is pinned to a **curated allow-list** of estimators, not
produced by calling `sklearn.utils.all_estimators()` at runtime. Why: `all_estimators()`
enumerates whatever the installed sklearn version happens to expose, which would make the
generated catalog non-deterministic across environments/versions — breaking the golden test on
the generated catalog (Story 7) and violating the "catalog is versioned" invariant already
established for the node catalog (this mirrors the precedent set in
[ADR 0015](./0015-node-catalog-and-export.md), decision 4, on `catalog_version`). New sklearn
versions or new estimators widen the allow-list only via a **reviewed change** (a PR that edits
the allow-list registry and regenerates the golden catalog artifact), never automatically at
import/runtime.

**6. Param-surface policy.** For each estimator in the allow-list, a **curated set of "common"
constructor kwargs** is exposed with defaults, help text, and UI hints (e.g. `n_estimators`,
`max_depth` for a random forest) — the small subset a user actually tunes day to day — while the
long tail of less-common sklearn constructor kwargs is reachable through a single
`advanced_params: dict` passthrough param on the node. This resolves the trade-off between
exposing every sklearn constructor kwarg individually (which would make config panels illegible —
some estimators have 15+ kwargs) and exposing only a fixed handful (which would silently hide
capability the underlying estimator actually supports). The curated-common + `advanced_params`
split keeps the common path legible without capping what's reachable.

## Consequences

**Positive:**

- ADR-0002 equivalence holds for the whole ~200-estimator catalog the moment it holds for the one
  adapter, instead of needing ~200 separate proofs.
- The node `type` enum stays at four archetypes forever, so the canvas palette schema and
  edge-validation rules never need to change as the catalog grows — only the allow-list data does.
- Adding a new sklearn estimator becomes a reviewed data change (allow-list entry + regenerated
  golden catalog), not a new Python file with its own test suite.

**Negative / obligations:**

- No individual estimator gets bespoke, idiomatic codegen — every generated script calls through
  the `ef.ml.*` adapter, which this ADR explicitly accepts as the cost of
  equivalence-by-construction.
- The curated allow-list and curated common-kwargs lists are themselves now maintenance surface —
  every new sklearn version requires a reviewed pass to decide what widens.
- The four archetypes' port shapes are now load-bearing for every future generated node — changing
  one later means touching every already-generated node's wiring and the canvas edge-validation
  rules built on it.

**Deferred:**

- "Transparent" native-sklearn codegen (subsection 4) — revisit only if there's real demand for
  prettier exported scripts, and only with its own per-estimator equivalence proof.
- The actual adapter implementation, registry, archetype nodes, catalog generation, and
  equivalence-test matrix — Stories 2 through 9, which build on the architecture locked here.
- Pipelines / hyperparameter search (`ml.pipeline`, `ml.grid_search`) — Story 8, explicitly gated
  behind Stories 2–7 landing.
