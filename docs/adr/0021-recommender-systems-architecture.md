# ADR 0021 — Recommender systems are a parallel `recommend` family with their own archetypes, representations, and optional-extra boundary — not an extension of the sklearn estimator adapter

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** SDK maintainers (proflandrigan)

## Context

The platform needs a recommender-systems surface (Epic 15) spanning baselines (random, popularity,
co-occurrence), content-based filtering (TF-IDF, feature KNN, embedding similarity), collaborative
filtering (user/item KNN, SVD, NMF, ALS, BPR), and deep recommenders (NCF, two-tower). The
architectural question is whether to route these through the existing `ml.fit_estimator` adapter
([ADR 0016](./0016-sklearn-estimator-adapter.md)) or build a parallel seam.

Four forces make the answer clear:

1. **Recommenders are not sklearn estimators.** The data shape is fundamentally different:
   recommenders consume sparse user-item interaction matrices, not feature-target DataFrames; their
   output is a ranked list of items per user, not a single prediction column; their API surface is
   `fit(interactions)` + `recommend(user_ids, n)`, not `fit(X, y)` + `predict(X)`. Forcing them
   through `fit_estimator` would be a leaky abstraction — the same lesson Epic 12 learned for
   statistical models, which led to a separate `stats` family rather than an `ml` subcategory.

2. **Interaction matrices are sparse — and that's load-bearing.** A 100k-user × 50k-item
   interaction matrix is 5 billion entries dense but typically <0.1% non-zero. Every algorithm must
   work with scipy sparse matrices; converting to dense is a correctness bug for any non-toy
   dataset. This requires a dedicated `InteractionMatrix` representation, not a `DataFrame`.

3. **Evaluation metrics are different in kind.** Recommender evaluation uses precision@k, recall@k,
   NDCG@k, MAP@k, hit rate, coverage, diversity, and novelty — ranking and system-level metrics
   that have no analog in classification/regression evaluation. Coverage and diversity in particular
   surface the failure mode where a trivially-high-precision recommender recommends the same 10
   popular items to everyone.

4. **The dependency boundary splits cleanly.** Baselines, content-based, evaluation, and
   sklearn-backed matrix factorization (SVD, NMF) all run on existing hard deps
   (scipy/sklearn/pandas/numpy). Optimized implicit-feedback models (`implicit`, MIT) and deep
   recommenders (`torch`) are optional extras with established `importorskip` discipline.

The rejected alternatives:

- **Extending `ml.fit_estimator` with a "recommender mode":** every recommender-specific concept
  (interaction matrices, ranked-list output, per-user evaluation, the `recommend()` verb itself)
  would need special-casing inside the sklearn adapter, violating its clean `fit(X, y)` /
  `predict(X)` contract.
- **A single generic `fit_recommender` adapter (mirroring `fit_estimator`):** recommender port
  shapes vary by family — baselines take only the interaction matrix; content-based nodes take the
  interaction matrix *and* an item-features DataFrame; deep models optionally take user-features and
  item-features DataFrames. A single adapter would accumulate a growing union of optional ports,
  exactly the parameter-explosion problem `fit_estimator` avoids by having one fixed port shape.
- **Pulling `surprise` (BSD-3):** less maintained, pure Python, slower than sklearn's own SVD/NMF
  for explicit ratings and `implicit` for implicit feedback. Adds a dependency without covering
  surface that the chosen libraries don't already handle.
- **Pulling `LensKit` (MIT):** heavy transitive dependencies, overlapping surface with our own
  wrappers + sklearn + `implicit`.
- **Pulling `RecBole` (MIT):** torch-only, overlaps with our own torch-optional deep-recommender
  path, and would force torch as a hard dependency of the `[recommend]` extra.

## Decision

**We will add `recommend` as a new `ef.*` family — a parallel seam to `ml` with its own
archetypes, inspectable representations, registry, and optional-extra boundary — following the
identical registry-mechanism + archetype + generated-catalog pattern so ADR-0002 equivalence and the
`@public_op` inspectable contract hold by construction.**

### 1. Three inspectable representations

- **`InteractionMatrix`** — a dataclass wrapping a scipy CSR sparse matrix + bidirectional user/item
  ID-to-index mappings + metadata (`n_users`, `n_items`, `n_interactions`, `density`,
  `explicit_vs_implicit` flag). Inspectable via a tidy summary dict on the result-payload contract;
  the raw sparse matrix is never serialized. Canonical constructor:
  `from_dataframe(df, *, user_col, item_col, value_col, implicit)`.

- **`FittedRecommender`** — a dataclass (all recommender archetypes ride inside one representation):
  `algorithm` (str), `algorithm_family` (str — `baseline` / `content` / `collaborative` / `deep`),
  `n_users` (int), `n_items` (int), `fit_stats` (dict — training metrics, sparsity, coverage),
  `model` (Any — live model object, degrades to `{"kind": "unsupported"}` on the result-payload
  contract, mirroring Epic 8's `FittedModel` and Epic 12's `FittedStatsModel`).

- **`RecommendationResult`** — wraps a tidy DataFrame (`user_id`, `item_id`, `rank`, `score`);
  JSON-native and round-trips through the result-payload contract untouched.

### 2. Four recommender archetypes (port shapes)

Recommenders do not share a single port shape. The four archetypes fix port shapes that the registry
and generated catalog enforce:

| Archetype | IN ports | OUT ports | Algorithms |
| :-------- | :------- | :-------- | :--------- |
| **baseline** | `InteractionMatrix` (+ params) | `Recommender` + tidy recommendation `DataFrame` | random, popularity (global/segmented), co-occurrence / association rules |
| **content-based** | `InteractionMatrix` + item-features `DataFrame` (+ params) | `Recommender` + tidy recommendation `DataFrame` | TF-IDF similarity, feature KNN, embedding similarity |
| **collaborative** | `InteractionMatrix` (+ params) | `Recommender` + tidy recommendation `DataFrame` | user KNN, item KNN, SVD, NMF, ALS, BPR |
| **deep** *(optional `torch`)* | `InteractionMatrix` (+ optional feature `DataFrame`s + params) | `Recommender` + tidy recommendation `DataFrame` | NCF, two-tower |

This is the same structural choice the codebase already made for statistical models (per-family
node types rather than one generic `fit_model`), applied to the recommender domain.

### 3. One wrapper per verb — ADR-0002 by construction

Three shared entry points in `emergentflow/recommend/`:

- `ef.recommend.fit(interactions, *, algorithm, **params) -> FittedRecommender` — every recommender
  node's `codegen` emits an `ef.recommend.fit(...)` call and its `execute` calls the same function.
- `ef.recommend.recommend(recommender, *, user_ids, n, exclude_known) -> RecommendationResult` —
  generates top-N recommendations.
- `ef.recommend.similar_items(recommender, *, item_ids, n) -> RecommendationResult` — item-item
  similarity for content-based and collaborative models that support it.

Every wrapper is a `@public_op` returning an inspectable value. The two pure functions
(`compile_to_code`, `execute`) both route through these wrappers, so ADR-0002 equivalence holds by
construction exactly as every other family achieves it.

### 4. Structured params, not raw config dicts

Recommender nodes take explicit, validated params (`user_col`, `item_col`, `value_col`, `algorithm`,
`n_recommendations`, `similarity_metric`, `k`, `n_components`, `seed`, etc.) rather than a raw
`**kwargs` / config dict passed through to the underlying library. The wrapper builds the library
call internally. This is the same trade-off the codebase already resolved for `ml` (validated on the
canvas config panel vs. raw flexibility) and `stats` (per-family structured specs).

### 5. Optional-extra boundary

| Scope | Deps | Install path |
| :---- | :--- | :----------- |
| Baselines, content-based, evaluation, memory-based CF, sklearn-backed SVD/NMF | scipy, sklearn, pandas, numpy (existing hard deps) | `pip install emergentflow` |
| Optimized implicit-feedback CF (ALS, BPR) | `implicit` (MIT, C++/Cython extensions, no torch) | `pip install emergentflow[recommend]` |
| Deep recommenders (NCF, two-tower) | `torch` (BSD, existing optional extra) | user installs torch ad hoc (never in `pyproject.toml`) |

The `[recommend]` extra adds `implicit` only. `torch` remains the existing ad-hoc optional.
Base-install use of an `implicit`-backed algorithm raises
`MissingOptionalDependencyError("emergentflow[recommend]")` — never an opaque `ImportError`.
Base-install use of a `torch`-backed deep recommender raises
`MissingOptionalDependencyError("torch")`. Both follow the discipline established by the `[bayes]`
and `[explain]` extras.

### 6. Type tokens

`Recommender` and `InteractionMatrix` are registered as new type tokens with Epic 3 compatibility
rules: a `Recommender` wires into recommend/evaluate/similar-items nodes but not into a `DataFrame`
input; an `InteractionMatrix` wires into recommender-fit nodes but not into a plain `DataFrame`
consumer. These are distinct from Epic 8's `Model` and Epic 12's `StatsModel`.

### 7. License and dependency hygiene

- scipy/sklearn/pandas/numpy: BSD (existing hard deps, no change).
- `implicit`: MIT (new `[recommend]` extra). No GPL. No torch dependency.
- `torch`: BSD (existing optional extra, unchanged).
- **Not pulled:** `surprise` (BSD-3, less maintained, overlapping surface), `LensKit` (MIT, heavy
  transitive deps), `RecBole` (MIT, torch-only, overlapping surface).

### 8. Determinism obligation

Fixed seeds pin every stochastic recommender for the equivalence gate:

- sklearn SVD/NMF: `random_state` param → deterministic.
- `implicit` ALS/BPR: `random_state` param → verify bitwise reproducibility; if parallel execution
  breaks it, document tolerance and assert exact match on ranked item order for top-k with
  well-separated scores, with an epsilon on scores.
- `torch` NCF/two-tower: `torch.manual_seed` + `torch.use_deterministic_algorithms(True)`.

Equivalence tests compare the inspectable recommendation DataFrame (`user_id`, `item_id`, `rank`,
`score`), not opaque model internals.

## Consequences

**Easier / positive**

- Every recommender algorithm inherits ADR-0002 equivalence, the `@public_op` inspectable contract,
  and generated-catalog inclusion by construction — the same structural guarantee `ml`, `stats`, and
  `explain` already provide.
- The four explicit archetypes prevent port-shape confusion on the canvas: a content-based node
  visibly requires two inputs (interactions + features), while a baseline needs only one.
- The `InteractionMatrix` type token prevents the most common recommender bug (accidentally wiring a
  raw DataFrame into an algorithm that expects a sparse interaction matrix).
- The base install ships a useful recommender surface (baselines, content-based, memory-based CF,
  sklearn-backed matrix factorization, full evaluation metrics) with zero new hard dependencies.
- Cold-start behavior is surfaced by the archetype system itself: content-based and hybrid
  recommenders handle cold-start; pure CF does not. This is metadata in the registry, not a runtime
  surprise.

**Harder / negative**

- A new top-level family means a new package (`emergentflow/recommend/`), new node archetypes in the
  registry, new type tokens, and new equivalence-test infrastructure — the same standing-up cost
  `stats` and `explain` incurred, but amortized across the algorithm matrix.
- Four archetypes is more surface than one generic adapter, but less surface than the
  parameter-explosion a single adapter would accumulate to cover the port-shape variance.
- The `[recommend]` extra is the fourth optional extra (`[llm]`, `[bayes]`, `[explain]`,
  `[recommend]`). Document it alongside the others in `docs/licensing-and-dependencies.md`.
- Determinism verification for `implicit`'s parallel ALS is a real obligation — if it can't be made
  bitwise-reproducible, the equivalence gate needs a documented score-epsilon with exact rank-order
  match, rather than the byte-identical comparison most other families enjoy.

**Deferred**

- **Online learning / bandit algorithms:** their own future epic; this epic ships offline training +
  evaluation only.
- **Real-time serving / model deployment:** FAISS/ScaNN ANN indices, model export to
  ONNX/TorchScript, real-time feature stores are out of scope. Document this boundary explicitly.
- **Session-based / sequential recommendation:** RNN/Transformer-based models over click sequences
  extend the two-tower architecture with attention; deferred to a follow-on epic.
- **Graph neural networks for CF:** GNN-based collaborative filtering is a distinct model family;
  deferred.
- **A/B testing infrastructure:** online experimentation over recommender outputs is a distinct
  concern; deferred.
- **Hybrid recommenders as a composition layer (Story 9):** weighted blending and cold-start
  switching over multiple fitted recommenders are a composition concern built atop the archetypes
  defined here — they do not change this ADR's decisions, but their multi-input port shape may be
  the first of its kind in the type system and will need documentation in `docs/type-system-spec.md`.
