# Epic 15 — Recommender Systems

> **Repo <-> roadmap numbering.** Epic files are numbered by **delivery order in this repo**; the
> [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**. This file
> is repo **Epic 15**. It introduces the `ef.recommend` family — a recommender-systems surface
> spanning baselines (random, popularity), content-based filtering, collaborative filtering (memory-
> based and model-based), embedding-based similarity search, and deep-learning recommenders (neural
> collaborative filtering, two-tower models). The family follows the same wrapper-routing +
> inspectable-representation + generated-catalog strategy proven by repo Epic 8 (scikit-learn) and
> repo Epic 12 (statistics/viz), adapted to the distinct data shape recommenders operate on:
> user-item interaction matrices rather than feature-target DataFrames.
> **Always qualify "repo Epic N" vs "roadmap Epic N"** — see [`epics/README.md`](./README.md).

> **The recommender surface has two distinct halves — and the architecture reflects that.**
> Recommender algorithms split cleanly into a "no new deps" half (baselines, content-based,
> evaluation metrics — all expressible with sklearn + scipy + pandas, which are already hard deps)
> and a "heavy optional deps" half (implicit-feedback matrix factorization via `implicit`, deep
> models via `torch`). This epic mirrors the Epic 12 Bayesian boundary: the base install ships the
> full baseline, content-based, and evaluation surface; heavier collaborative-filtering and
> deep-learning models are gated behind optional extras (`[recommend]`, `torch`) with the same
> `importorskip` / typed-error discipline.
>
> The second structural bet: recommenders are **not** sklearn estimators. They consume interaction
> matrices (sparse user x item), not feature-target DataFrames; their output is a ranked list of
> items per user, not a single prediction column. Forcing them through the Epic 8 `fit_estimator`
> adapter would be a leaky abstraction — the same lesson Epic 12 learned for statistical models.
> Instead we build a **parallel but structurally analogous** seam: `ef.recommend` gets its own
> registry, its own `FittedRecommender` representation, and its own wrapper functions, but follows
> the identical registry-mechanism + archetype + generated-catalog pattern so the ADR-0002
> equivalence and `@public_op` inspectable contract hold by construction.

**Phase:** Follows repo Epic 8 (the estimator-adapter + generated-catalog pattern this epic reuses
structurally), repo Epic 12 (the `FittedStatsModel` / optional-extra / archetype-not-adapter
precedent), and repo Epic 9 (the `ef.llm` seam whose embedding capabilities this epic consumes for
embedding-based similarity). Sequenced after these so the recommender layer can leverage existing
sklearn transforms (Epic 8's `fit_transform` for feature engineering), the viz layer (Epic 12's
`PlotSpec` for recommendation diagnostics), and the LLM client seam (Epic 9's embedding support
for content-based filtering over dense vectors).
**Lives in:** `emergentflow/` — the SDK tree owns the recommender wrappers
(`emergentflow/recommend/`), the new node archetypes (`emergentflow/nodes/`), the generated
recommender-catalog entries, the new inspectable representations, and the type tokens. The canvas
palette + config panels (`ui/`, repo Epic 5) **only consume** the generated catalog — **no
per-algorithm UI is written here**.
**Dependencies:** Epic 1 (node contract, param schema, registry, `@register`), Epic 2
(`compile_to_code` / `execute` + the golden/equivalence harness), Epic 3 / roadmap 5 (type tokens +
rules-as-data so `Recommender`/`InteractionMatrix` ports validate), Epic 8 (`FittedModel` precedent;
the adapter + generated-catalog pattern; sklearn transforms for feature engineering), Epic 9 (LLM
client seam for embeddings — consumed, not modified). `scipy`, `pandas`, `scikit-learn`, `numpy`
are **already** runtime deps. New deps introduced: **none** as hard deps (baselines, content-based,
evaluation, and sklearn-backed matrix factorization all run on existing deps). **`implicit`
(MIT)** as an optional `[recommend]` extra for optimized implicit-feedback ALS/BPR. **`torch`**
(already an optional extra, never in `pyproject.toml`) for deep recommenders (two-tower, NCF).
**Blocks:** future personalization / A/B-test / online-learning epics (this epic ships the offline
training + evaluation surface they build on), and raises the quality ceiling of the roadmap Epic 12
NL->graph agent (the recommender surface it can target widens).

---

## Definition of Done (epic-level)

- [ ] **Baseline recommenders:** random, popularity (global and segmented), and association-rule
  (co-occurrence / lift) recommenders are each reachable as nodes, requiring no deps beyond the
  existing hard deps. Each returns a `RecommendationResult` — a ranked list of item IDs + scores
  per user, inspectable and JSON-native.
- [ ] **Content-based filtering:** TF-IDF + cosine-similarity over item text features, feature-
  vector nearest-neighbors (sklearn `NearestNeighbors`), and embedding-based similarity search
  (consuming dense vectors from `ef.llm.embed` or a user-supplied embedding column) are reachable
  as nodes, all via the base install.
- [ ] **Collaborative filtering — memory-based:** user-based and item-based KNN collaborative
  filtering (cosine / Pearson similarity over the interaction matrix, sklearn/scipy-backed) ships
  in the base install.
- [ ] **Collaborative filtering — model-based (base):** sklearn-backed matrix factorization
  (TruncatedSVD, NMF) over the interaction matrix ships in the base install as a baseline
  model-based CF path.
- [ ] **Collaborative filtering — model-based (optional):** optimized implicit-feedback matrix
  factorization (ALS, BPR) via `implicit` ships behind `pip install emergentflow[recommend]`;
  the base install never imports `implicit`, base-install use of an `implicit`-backed algorithm
  raises a **clear, typed "install the `[recommend]` extra" error**, and equivalence tests use
  the `importorskip` discipline so CI's default lane never needs the heavy stack.
- [ ] **Deep recommenders (optional, stretch):** neural collaborative filtering (NCF) and two-
  tower models ship behind `torch` (already optional, never in `pyproject.toml`); base-install use
  raises a typed `MissingOptionalDependencyError("torch")`; equivalence tests use
  `pytest.importorskip("torch")`. Fixed seeds + fixed data for determinism.
- [ ] **Evaluation metrics:** precision@k, recall@k, NDCG@k, MAP@k, hit rate, coverage, and
  diversity are available as `ef.recommend.evaluate` returning a tidy metrics DataFrame —
  inspectable, JSON-native, no new deps.
- [ ] **Interaction-matrix preparation is a first-class node:** a `prepare_interactions` node
  transforms a tidy event/rating DataFrame (user_col, item_col, value_col) into the sparse
  `InteractionMatrix` the recommender nodes consume, with configurable implicit/explicit mode
  and optional value thresholding.
- [ ] **The inspectable contract holds everywhere:** every recommender node returns a
  `FittedRecommender` whose live-model field degrades to `{"kind": "unsupported"}` on the
  result-payload contract, alongside a tidy **recommendation DataFrame** (user_id, item_id,
  rank, score) and a **metrics DataFrame** (from evaluation). A live `implicit`/`torch` model
  object is **never** dumped into a response.
- [ ] **ADR-0002 holds by construction:** `codegen` and `execute` for every node route through the
  same `ef.recommend.*` wrapper; both stay **pure** (no I/O, no global state) — fitted recommenders
  and recommendation lists flow in-memory under `execute` and as plain variables in compiled code.
  A **parametrized equivalence harness** proves it over the algorithm matrix (keyed on the
  inspectable recommendation/metrics DataFrame, so opaque model internals aren't compared), gated
  in CI alongside the existing equivalence gate. Determinism is pinned with fixed seeds.
- [ ] **New type tokens registered** (`Recommender`, `InteractionMatrix`) with Epic 3 compatibility
  rules so a fitted recommender wires into an evaluate/recommend node but not into a `DataFrame`
  input, and an `InteractionMatrix` wires into recommender-fit nodes but not into a plain
  `DataFrame` consumer.
- [ ] **License hygiene:** scipy/sklearn/pandas/numpy (BSD), implicit (MIT), torch (BSD) — **no
  GPL** deps; `surprise` is deliberately not pulled (sklearn + implicit cover the surface; surprise
  is less maintained and would add an unnecessary dep).
- [ ] **Acceptance demos (Story 15):** (a) a **content-based** flow — `load -> prepare_interactions
  -> popularity baseline -> content-based (TF-IDF) -> evaluate -> comparison bar chart` — and (b)
  a **collaborative filtering** flow — `load -> prepare_interactions -> user-KNN CF ->
  matrix-factorization CF -> evaluate -> recommendation list` — both build on the canvas, compile
  to `.py`, and execute end-to-end.
- [ ] **Explicitly out of scope:** online learning / bandit algorithms (their own future epic),
  reinforcement-learning-based recommendation, real-time serving / model deployment, A/B testing
  infrastructure, knowledge-graph-based recommendation, session-based / sequential recommendation
  (RNNs/Transformers over click sequences), and the graph neural network family (GNN-based CF).

---

## Story group A — Foundations (the load-bearing seams)

## Story 1 — Lock the recommend architecture

> Cheap to decide, expensive to retrofit across the algorithm surface. No ADR is required (per
> request), but capture these decisions in a design note (`docs/recommend-design.md`) before
> building — this is the Epic-8-Story-1 / Epic-12-Story-1 equivalent.

- [ ] **One inspectable representation, decided up front.** `FittedRecommender` (one dataclass all
  recommender archetypes ride inside: algorithm kind, structured spec echo, a tidy `recommendations`
  frame — user_id, item_id, rank, score — `fit_stats` dict — n_users/n_items/n_interactions/
  sparsity/coverage — and a live-model field that degrades to `{"kind": "unsupported"}` on the
  result-payload contract, mirroring Epic 8's `FittedModel` and Epic 12's `FittedStatsModel`).
  `InteractionMatrix` (a thin wrapper over a scipy sparse matrix + user/item index mappings,
  inspectable via a tidy summary — n_users, n_items, n_interactions, sparsity, density — never the
  raw sparse data). `RecommendationResult` (a tidy DataFrame of user_id, item_id, rank, score —
  JSON-native, the terminal recommendation payload).
- [ ] **Recommender archetypes (not one generic adapter).** Fix four port shapes now, and record
  *why* we do **not** force recommenders through the Epic 8 sklearn adapter (recommenders consume
  interaction matrices, not feature-target DataFrames; their output is a ranked list, not a
  prediction column; the API surface is `fit(interactions)` + `recommend(user_ids, n)`, not
  `fit(X, y)` + `predict(X)`):
  - **baseline:** `InteractionMatrix (+ params)` -> `Recommender` + tidy recommendation
    `DataFrame` — random, popularity, association-rule.
  - **content-based:** `InteractionMatrix + item-features DataFrame (+ params)` -> `Recommender`
    + tidy recommendation `DataFrame` — TF-IDF similarity, feature KNN, embedding similarity.
  - **collaborative:** `InteractionMatrix (+ params)` -> `Recommender` + tidy recommendation
    `DataFrame` — user KNN, item KNN, SVD, NMF, ALS, BPR.
  - **deep** *(optional `torch`)*: `InteractionMatrix (+ optional feature DataFrames + params)` ->
    `Recommender` + tidy recommendation `DataFrame` — NCF, two-tower.
- [ ] **Structured params over raw config dicts.** Recommender nodes take explicit `user_col` /
  `item_col` / `value_col` / `algorithm` / `n_recommendations` / `similarity_metric` / etc. as
  structured params; the wrapper builds the underlying library call internally. Record this
  decision and the trade-off (validated on the canvas vs. raw flexibility).
- [ ] **Optional extras, decided as a hard boundary.** `implicit` lives only under
  `pip install emergentflow[recommend]`; `torch` remains the existing optional extra. The base
  package must import and run with both absent. A recommender node backed by `implicit` in a base
  install raises a typed `MissingOptionalDependencyError("emergentflow[recommend]")` — never an
  opaque `ImportError`. Record the determinism obligation (fixed seed so matrix factorization
  results are reproducible for the equivalence gate).
- [ ] **Dependency & license decisions.** Add the `[recommend]` extra (`implicit`, MIT) to
  `pyproject.toml`; document in `docs/licensing-and-dependencies.md` with the same rigor as the
  `[bayes]` note. **No GPL** — call out that `surprise` (BSD-3 but less maintained) is *not*
  pulled (sklearn + implicit cover the surface). No `LensKit` (MIT but heavy transitive deps).
  No `RecBole` (MIT but torch-only, overlaps with our own torch-optional path).

---

## Story 2 — Inspectable representations + the wrapper seams (`emergentflow/recommend/`)

> Build the shared representations + the single wrapper each node routes through. This is the
> load-bearing seam: get it right and every algorithm inherits ADR-0002 equivalence and the
> `@public_op` inspectable contract — exactly the Epic 8 Story 2 / Epic 12 Story 2 pattern.

- [ ] Implement `InteractionMatrix` as a dataclass wrapping a scipy CSR sparse matrix + user/item
  ID-to-index mappings (bidirectional) + metadata (n_users, n_items, n_interactions, density,
  explicit-vs-implicit flag). Inspectable via a tidy summary dict on the result-payload contract;
  the raw sparse matrix is **never** serialized. Provide `from_dataframe(df, *, user_col, item_col,
  value_col, implicit)` as the canonical constructor from a tidy events/ratings DataFrame.
- [ ] Implement `FittedRecommender` (+ per-algorithm-family fields where needed) as a dataclass
  whose live-model field degrades to `{"kind": "unsupported"}` on the result-payload contract.
  Confirm the degrade path against the Epic 8/12 precedent. Fields: `algorithm` (str),
  `algorithm_family` (str — baseline/content/collaborative/deep), `n_users` (int), `n_items` (int),
  `fit_stats` (dict — training metrics, sparsity, coverage), `model` (Any — live model object).
- [ ] Implement `RecommendationResult` wrapping a tidy DataFrame (user_id, item_id, rank, score);
  confirm it is JSON-native and round-trips through the result-payload contract untouched.
- [ ] `ef.recommend.fit(interactions, *, algorithm, params) -> FittedRecommender` — validates the
  algorithm key + params, fits the model on the interaction matrix, and wraps the live model in
  `FittedRecommender` with fit stats. One function; every recommender node's `codegen` emits an
  `ef.recommend.fit(...)` call and its `execute` calls the same function -> ADR-0002 by
  construction.
- [ ] `ef.recommend.recommend(recommender, *, user_ids, n, exclude_known) ->
  RecommendationResult` — generates top-N recommendations for the given users (or all users),
  optionally excluding items already in the training interactions. One function; every recommend
  node routes through it.
- [ ] `ef.recommend.similar_items(recommender, *, item_ids, n) -> RecommendationResult` —
  returns the N most similar items to each given item, for content-based and collaborative models
  that support item-item similarity.
- [ ] Every wrapper is a `@public_op` returning an inspectable value. Unit tests on the seams
  themselves: unknown algorithm key -> typed error; bad params -> typed error; determinism given
  a fixed seed; **no input mutation**; live object never present in the serialized payload.

---

## Story 3 — Type tokens, interaction-data preparation & the shared validation gate

> Structural validation and recommendation both key off type tokens + the interaction matrix shape.
> Register them before the algorithm families widen so every new node validates for free. Mirror
> Epic 8 Story 3 / Epic 12 Story 3.

- [ ] Register `Recommender` (a fitted recommender model — distinct from Epic 8's `Model` and
  Epic 12's `StatsModel`) and `InteractionMatrix` (a prepared user-item interaction dataset) type
  tokens; add Epic 3 rules-as-data compatibility rows to `docs/type-system-spec.md` (a
  `Recommender` wires into recommend/evaluate/similar-items nodes, not into a `DataFrame` input;
  an `InteractionMatrix` wires into recommender-fit nodes, not into a plain `DataFrame` consumer).
- [ ] Implement `_prepare_interactions` — the **single** interaction-data validation gate shared by
  both `codegen` and `execute` (as `_prepare_declarative` is shared by the compiler and executor /
  `_prepare_model_spec` is shared by stats models): user column exists, item column exists, value
  column exists (or defaults to 1 for implicit), no duplicate user-item pairs (or aggregation
  strategy: sum/mean/max/last), minimum interaction count filters (per-user and per-item), and
  cold-start handling mode (error / warn-and-skip / include).
- [ ] Implement the `prepare_interactions` node: `DataFrame (+ user_col, item_col, value_col,
  implicit flag, min_user_interactions, min_item_interactions)` -> `InteractionMatrix`. This is
  the recommender family's analog to `train_test_split` — the data-shape boundary between tidy
  DataFrames and the sparse interaction world.
- [ ] **Temporal train/test splitting for recommenders.** `ef.recommend.temporal_split(interactions,
  *, timestamp_col, test_ratio)` -> `(train_interactions, test_interactions)` — splits by
  timestamp (each user's last N% of interactions go to test), the standard recommender evaluation
  split. Also provide a random split as a simpler alternative. Both return `InteractionMatrix`
  pairs.

---

## Story group B — Baseline & content-based recommenders (no new deps)

## Story 4 — Baseline recommenders (random, popularity, co-occurrence)

> The simplest recommenders — zero learning, pure heuristics. Every production recommender system
> starts here as the baseline to beat. All run on existing hard deps (pandas/numpy/scipy).

- [ ] **Registry entries** for the baseline archetype:
  - **Random:** recommends N random items per user, optionally weighted by item frequency. Params:
    `n`, `seed`. Deterministic given `seed`.
  - **Popularity (global):** recommends the N most-interacted-with items globally, the same list
    for every user. Params: `n`, `score_type` (count / mean_rating / weighted).
  - **Popularity (segmented):** popularity within a user segment (a segment column on the user
    DataFrame). Params: `n`, `segment_col`, `score_type`.
  - **Co-occurrence / association rules:** for each item a user has interacted with, find items
    frequently co-occurring (lift / confidence / support). Params: `n`, `metric` (lift /
    confidence / support), `min_support`.
- [ ] Each baseline node emits `FittedRecommender` (with `algorithm_family="baseline"`) + a tidy
  recommendation `DataFrame`. The `FittedRecommender.model` for baselines is a lightweight dict/
  DataFrame (item scores, co-occurrence matrix) — no external model object.
- [ ] Golden `ast.parse` + `ruff check` on a representative baseline (a popularity graph via a
  real `load_sample -> prepare_interactions -> fit -> recommend` graph), plus the parametrized
  equivalence slice (Story 13) over the baseline keys.

## Story 5 — Content-based filtering (TF-IDF, feature KNN, embedding similarity)

> Recommenders that leverage item (and optionally user) features rather than interaction patterns.
> All backed by sklearn / scipy — no new deps.

- [ ] **Registry entries** for the content-based archetype:
  - **TF-IDF + cosine similarity:** given a text-feature column on items (title, description,
    tags), builds a TF-IDF matrix and recommends items most similar (cosine) to a user's
    interaction history (centroid of interacted-item TF-IDF vectors). Params: `text_col`,
    `n`, `max_features`, `ngram_range`.
  - **Feature-vector nearest neighbors:** given a numeric feature matrix for items (pre-computed
    or from item metadata columns), recommends the nearest items to the user's profile
    (mean of interacted-item feature vectors) via sklearn `NearestNeighbors`. Params:
    `feature_cols`, `n`, `metric` (cosine / euclidean), `algorithm` (ball_tree / kd_tree / brute).
  - **Embedding similarity:** given a dense embedding column (produced by `ef.llm.embed` or
    user-supplied), recommends items whose embeddings are nearest to the user's profile embedding
    (mean of interacted-item embeddings). Params: `embedding_col`, `n`, `metric`.
- [ ] Content-based nodes take **two** inputs: the `InteractionMatrix` (who interacted with what)
  **and** an item-features `DataFrame` (the content to match on). The port shape is distinct from
  baselines (which need only the interaction matrix) and from collaborative filtering (which needs
  only the interaction matrix). Record this as a deliberate archetype-shape decision, not a
  limitation.
- [ ] Golden + equivalence via the Story 13 harness on fixtures with known text/feature data and a
  fixed seed for TF-IDF vectorization.

## Story 6 — Embedding-based similarity with the `ef.llm` seam

> Bridge to repo Epic 9: leverage `ef.llm.embed` (or any user-supplied embedding column) for
> dense-vector similarity search over items. This story wires the content-based archetype to the
> existing LLM client seam — it does **not** build a new embedding pipeline.

- [ ] A `recommend_by_embedding` node that: (a) accepts an item-features DataFrame with a
  pre-computed embedding column (a list/array of floats per row), (b) builds an item-item
  similarity index (sklearn `NearestNeighbors` with cosine metric over the embedding matrix), and
  (c) recommends items similar to a user's interaction profile (mean embedding of interacted
  items). This is the **content-based archetype** with the feature source being a dense embedding
  rather than sparse TF-IDF — same port shape, same `FittedRecommender` output.
- [ ] An **optional convenience node** (compose, not duplicate): `embed_then_recommend` wires
  `ef.llm.embed` (to produce the embedding column) -> `recommend_by_embedding` as a single
  compound step. This is a graph-composition shortcut surfaced as a single node in the palette,
  not a separate implementation — it decomposes to two existing wrappers. `requires_client = True`
  (ADR 0017) since it invokes the LLM client for embedding. Record that users can also wire the
  two steps manually in the graph.
- [ ] If `ef.llm.embed` is not available (no `[llm]` extra installed), the `embed_then_recommend`
  node raises `MissingOptionalDependencyError("emergentflow[llm]")`; the bare
  `recommend_by_embedding` node works with any pre-computed embedding column and needs no optional
  extras.
- [ ] Golden + equivalence tests use `ReplayClient` fixtures (the existing llm test discipline)
  for the `embed_then_recommend` path, and fixed synthetic embeddings for the bare
  `recommend_by_embedding` path.

---

## Story group C — Collaborative filtering

## Story 7 — Memory-based collaborative filtering (user KNN, item KNN)

> The classical CF algorithms: find similar users (or similar items) via direct similarity
> computation over the interaction matrix. All backed by scipy sparse operations + sklearn
> pairwise distances — no new deps.

- [ ] **Registry entries** for the collaborative archetype (memory-based sub-family):
  - **User-based KNN CF:** for each user, find the K most similar users (cosine / Pearson over
    their interaction vectors), then recommend items those similar users liked that the target user
    hasn't seen. Params: `k` (neighbors), `similarity` (cosine / pearson / jaccard), `n`
    (recommendations), `min_common_items` (minimum overlap to consider a user pair).
  - **Item-based KNN CF:** for each item pair, compute similarity over their user-interaction
    vectors; for a target user, score unseen items by weighted similarity to items they've
    interacted with. Params: `k`, `similarity`, `n`, `min_common_users`.
- [ ] Both memory-based CF algorithms operate directly on the `InteractionMatrix` sparse matrix.
  The similarity computation uses `sklearn.metrics.pairwise.cosine_similarity` (sparse-aware) for
  cosine, scipy's sparse correlation for Pearson, and set-intersection-over-union for Jaccard.
  For large matrices (>100k users/items), document the memory/time trade-off and recommend the
  model-based path (Story 8) instead.
- [ ] The `FittedRecommender.model` for memory-based CF stores the precomputed similarity matrix
  (sparse, thresholded to top-K per row to bound memory). `fit_stats` includes similarity-matrix
  density and the effective neighborhood size distribution.
- [ ] Golden + equivalence via the Story 13 harness on a small, deterministic interaction fixture.

## Story 8 — Model-based collaborative filtering (SVD, NMF, ALS, BPR)

> Matrix-factorization approaches: decompose the interaction matrix into latent user and item
> factor matrices. The base install covers sklearn-backed SVD/NMF (explicit ratings); the
> `[recommend]` extra adds optimized implicit-feedback models via `implicit`.

- [ ] **Base-install registry entries** (sklearn, no new deps):
  - **TruncatedSVD:** sklearn `TruncatedSVD` over the interaction matrix — learns latent factors
    for items. Reconstruct approximate ratings as `U @ Sigma @ Vt`, rank unseen items by
    predicted rating. Params: `n_components`, `n`, `seed`.
  - **NMF:** sklearn `NMF` over the (non-negative) interaction matrix — learns non-negative latent
    factors. Params: `n_components`, `n`, `seed`, `max_iter`.
- [ ] **`[recommend]`-extra registry entries** (`implicit`, MIT):
  - **ALS (Alternating Least Squares):** `implicit.als.AlternatingLeastSquares` — the standard
    implicit-feedback matrix factorization. Params: `factors`, `regularization`, `iterations`,
    `n`, `seed`. Deterministic given `seed`.
  - **BPR (Bayesian Personalized Ranking):** `implicit.bpr.BayesianPersonalizedRanking` — learns
    a ranking over items from pairwise implicit feedback. Params: `factors`, `learning_rate`,
    `regularization`, `iterations`, `n`, `seed`.
- [ ] The `FittedRecommender.model` for model-based CF stores the learned user-factor and item-
  factor matrices (numpy arrays, inspectable by shape; the live `implicit` model object degrades
  on the result-payload contract). `fit_stats` includes explained variance (for SVD),
  reconstruction error, and convergence info.
- [ ] **Optional-dependency discipline** (mirroring Epic 12 Story 7): base install absent-import
  -> typed `MissingOptionalDependencyError("emergentflow[recommend]")`; equivalence/golden tests
  use `pytest.importorskip("implicit")` so the default CI lane skips them; a **separate CI job**
  (or opt-in marker) installs `[recommend]` and runs the implicit-feedback equivalence matrix
  with fixed seeds.
- [ ] Golden + equivalence via the Story 13 harness. SVD/NMF are deterministic given a fixed seed.
  ALS/BPR determinism requires `implicit`'s `random_state` param — verify and document.

## Story 9 — Hybrid recommenders (content + collaborative)

> Combine content-based and collaborative signals. This story is a **composition layer**, not a new
> algorithm family — it wires existing recommenders together via score blending / stacking, so it
> inherits their ADR-0002 equivalence by construction.

- [ ] **Weighted hybrid:** given two or more `FittedRecommender` outputs (from any archetype), blend
  their per-item scores with configurable weights and re-rank. Params: `weights` (list of floats,
  one per input recommender), `n`, `blend_strategy` (weighted_sum / rank_fusion / cascade).
  This is the simplest and most common hybrid approach.
- [ ] **Switching hybrid:** select which recommender to use per user based on a condition (e.g.,
  cold-start users — fewer than K interactions — get the content-based recommender; warm users get
  collaborative). Params: `cold_start_threshold`, `n`. Addresses the cold-start problem directly.
- [ ] Both hybrid nodes take **multiple** `Recommender` inputs (or `RecommendationResult` frames)
  and emit a single `RecommendationResult`. The port shape is `Recommender[] + params ->
  RecommendationResult`; if this multi-input port is the first of its kind in the type system,
  document the extension in `docs/type-system-spec.md`.
- [ ] Golden + equivalence via the Story 13 harness, verifying that the blended output is
  deterministic and that the same blend weights produce identical results via `execute` and
  `compile_to_code`.

---

## Story group D — Deep recommenders *(optional `torch`; stretch / gated)*

## Story 10 — Neural collaborative filtering *(optional `torch`)*

> Learned interaction functions (MLPs replacing the dot product in matrix factorization). Gated
> behind Stories 2-8 landing **and** `torch` being available (the existing `importorskip`
> discipline).

- [ ] **NCF (Neural Collaborative Filtering):** a GMF (Generalized Matrix Factorization) + MLP
  architecture that learns user and item embeddings and a nonlinear interaction function. The
  implementation follows the He et al. 2017 paper. Params: `embedding_dim`, `mlp_layers` (list
  of hidden sizes), `epochs`, `batch_size`, `learning_rate`, `seed`. Deterministic given
  `seed` + `torch.manual_seed`.
- [ ] The model is a `torch.nn.Module` subclass, but the node wraps it inside `FittedRecommender`
  — the live module degrades on the result-payload contract, exactly like the declarative
  `nn.module` paradigm (Epic 2, ADR 0003). Training happens in `ef.recommend.fit()`; inference
  in `ef.recommend.recommend()` — both route through the same wrapper.
- [ ] **Optional-dependency discipline:** `torch` absent -> typed
  `MissingOptionalDependencyError("torch")`; tests use `pytest.importorskip("torch")`.
  Determinism pinned with `torch.manual_seed` + `torch.use_deterministic_algorithms(True)`.
- [ ] Golden + equivalence via the Story 13 harness (under a `torch`-available CI job).
  **Deferred:** attention-based models (Transformers for sequential recommendation),
  graph neural networks (GNN-based CF), variational autoencoders for CF.

## Story 11 — Two-tower retrieval model *(optional `torch`)*

> The production retrieval architecture: separate user and item encoder towers whose dot product
> approximates relevance. This is the architecture behind YouTube DNN, Google's retrieval stack,
> and most large-scale recommendation systems.

- [ ] **Two-tower model:** separate user-tower and item-tower encoders (configurable MLP
  architectures), trained with a contrastive or softmax loss over user-item interaction pairs.
  Params: `user_embedding_dim`, `item_embedding_dim`, `user_tower_layers`, `item_tower_layers`,
  `loss` (bce / softmax_cross_entropy / bpr_loss), `negative_sampling_ratio`, `epochs`,
  `batch_size`, `learning_rate`, `seed`.
- [ ] **Side features:** the two-tower model optionally consumes user-feature and item-feature
  DataFrames (concatenated with learned embeddings at the tower input). This is the key
  architectural advantage over pure collaborative filtering — the model can incorporate content
  signals and generalize to cold-start users/items.
- [ ] At inference time, item-tower embeddings are precomputed; user-tower embeddings are computed
  on-the-fly. Recommendations are generated by approximate nearest-neighbor search over the item
  embedding space (using sklearn `NearestNeighbors` as the base-install ANN index; document that
  production deployments would use FAISS/ScaNN, which are out of scope for this epic).
- [ ] Golden + equivalence via the Story 13 harness (under a `torch`-available CI job).
  **Deferred:** multi-task learning (engagement + satisfaction objectives), sequence-aware towers
  (attention over interaction history), FAISS/ScaNN ANN indices, model export to ONNX/TorchScript
  for serving.

---

## Story group E — Evaluation, testing & the payoff

## Story 12 — Recommendation evaluation metrics

> The metrics surface an analyst uses to compare recommenders. All backed by pandas/numpy — no
> new deps. This is the recommender analog to Epic 8's `ef.ml.evaluate`.

- [ ] `ef.recommend.evaluate(recommender, test_interactions, *, k, metrics) -> EvalResult` —
  scores a fitted recommender's recommendations against held-out interactions. Returns a tidy
  `EvalResult` dataclass containing:
  - **Per-user metrics frame:** user_id, precision_at_k, recall_at_k, ndcg_at_k, hit (binary),
    average_precision.
  - **Aggregate metrics dict:** mean precision@k, mean recall@k, mean NDCG@k, MAP@k, hit_rate,
    coverage (fraction of items ever recommended), diversity (intra-list distance), novelty
    (mean inverse popularity of recommended items).
  - `k` is configurable (default 10). `metrics` allows selecting a subset.
- [ ] **Coverage and diversity** are system-level metrics (not per-user): coverage measures catalog
  breadth (what fraction of all items appear in any user's top-k), diversity measures how
  different each user's recommendations are from each other (1 - mean pairwise cosine similarity
  of recommended item sets). Novelty rewards recommending long-tail items. These are the metrics
  that distinguish a trivially-high-precision "recommend the same 10 popular items to everyone"
  from a useful recommender.
- [ ] `ef.recommend.compare(test_interactions, *, recommenders, k) -> DataFrame` — the recommender
  analog to `ef.ml.compare_models`: evaluates multiple fitted recommenders on the same test set
  and returns a tidy comparison DataFrame (one row per recommender, columns for each metric),
  sorted by NDCG@k descending. The baseline-to-beat framing: a popularity recommender is always
  included as an automatic baseline row if not already in the list.
- [ ] Golden tests on the metric computations against known-correct hand-computed fixtures (small
  enough to verify by inspection). Confirm every metric is deterministic.

## Story 13 — Equivalence & golden testing at scale

> ADR-0002 is a CI gate. With a generated recommender catalog and an algorithm matrix we prove it
> with a **parametrized harness over the matrix**, keyed on the inspectable recommendation DataFrame
> — not one bespoke test per algorithm. Mirror Epic 8 Story 9 / Epic 12 Story 10.

- [ ] A `pytest.mark.parametrize` matrix that, per algorithm, builds a minimal graph
  (`prepare_interactions -> fit -> recommend`) and asserts `execute(ir)` artifacts ~= running
  `compile_to_code(ir)` on a fixed interaction fixture — keyed on the tidy recommendation
  DataFrame (user_id, item_id, rank, score) so opaque model internals aren't compared. Compute
  the matrix dynamically from the registry (it grows as the allow-list widens — the Epic 8
  `keys_for_archetype()` pattern).
- [ ] Fixed seeds + fixed interaction datasets for determinism; mark every equivalence test
  `@pytest.mark.equivalence` and gate it in `.github/workflows/ci.yml` alongside the existing
  equivalence gate. `[recommend]`-extra equivalence runs under a separate CI job with
  `pytest.importorskip("implicit")`. `torch`-backed equivalence runs under the existing
  `torch`-available job.
- [ ] Golden tests on **generated code** for a representative algorithm per archetype and family
  (readable, ruff-clean, importable) — not one golden per entry.

## Story 14 — Recommender-aware visualization nodes

> The plots that make the recommender evaluation legible — they read evaluation results and
> recommendation lists, not just raw DataFrames. This is where the recommend + viz halves meet,
> mirroring Epic 12 Story 9.

- [ ] **Precision-recall@k curve** from an `EvalResult` across multiple k values (sweep k=1..50
  and plot the trade-off). Emits `PlotSpec` (plotly, JSON-native, Epic 12 contract).
- [ ] **Metric comparison bar chart** from `ef.recommend.compare` output — one grouped bar per
  recommender, one color per metric. Emits `PlotSpec`.
- [ ] **Coverage vs. accuracy scatter** — plots each recommender's coverage against its NDCG@k,
  surfacing the accuracy/diversity trade-off. Emits `PlotSpec`.
- [ ] **Item popularity distribution** — long-tail histogram of recommendation frequency vs. item
  popularity rank (log scale), showing whether a recommender is biased toward popular items.
  Emits `PlotSpec`.
- [ ] Golden + equivalence via the Story 13 harness on fixtures that produce fitted recommenders
  first (so the plot node's input is a real `EvalResult`/DataFrame, not a stub).

## Story 15 — Wire into the canvas + acceptance demos

> The payoff: the generated catalog drives the palette and config panels with zero per-node UI,
> and real recommender workflows run end-to-end. Mirror Epic 8 Story 10 / Epic 12 Story 12.

- [ ] The canvas palette (repo Epic 5) renders every generated recommender entry and the
  evaluation/preparation nodes by `family`/`category` grouping; config panels render the
  structured spec (`user_col`/`item_col`/`value_col`/`algorithm`/`n`/`k`/`similarity`) from
  catalog data with **zero per-node UI code** (reuse/extend the Epic 8 Story 10 curated-per-field
  config renderer). Confirm `Recommender`- and `InteractionMatrix`-bearing edges validate on the
  canvas (Epic 3 rules).
- [ ] Round-trip canvas -> IR -> `/compile` -> downloadable `.py` and `/execute` with per-node
  status, including a `Recommender`-bearing edge (fit -> recommend) and a
  `RecommendationResult`-terminal edge.
- [ ] **Acceptance demo (content-based):** `load_sample -> prepare_interactions -> popularity
  baseline -> TF-IDF content-based -> evaluate both -> comparison bar chart` builds on the canvas,
  compiles, and executes to a metrics comparison table + a rendered bar chart.
- [ ] **Acceptance demo (collaborative filtering):** `load_sample -> prepare_interactions ->
  temporal_split -> user-KNN CF -> SVD CF -> evaluate both on test set -> recommendation list +
  precision-recall curve` builds on the canvas, compiles, and executes to recommendation
  DataFrames + evaluation metrics + a rendered plot.
- [ ] Document both under `docs/acceptance-demo.md` as the "recommender workflows the app can do
  today" reference, and add an example graph pair under
  `examples/recommender_acceptance_demo/` (the Epic 8
  `examples/sklearn_acceptance_demo/` precedent).

---

## Notes / Risks (carry into planning)

- **Recommenders are not sklearn estimators — don't pretend they are.** The `fit(X, y) ->
  predict(X)` paradigm doesn't apply: recommenders consume sparse interaction matrices, output
  ranked lists, and their evaluation metrics (precision@k, NDCG@k) are fundamentally different
  from classification/regression metrics. The Epic 8 adapter is the wrong seam. Build a parallel
  seam with the same structural properties (registry, archetypes, wrapper routing, inspectable
  representation, generated catalog) but the right data shapes. The uniformity we need comes from
  the **shared `FittedRecommender` representation + shared `ef.recommend.*` wrappers**, not from
  shoehorning recommenders into `fit_estimator`.
- **Interaction matrices are sparse — and that's load-bearing.** A 100k-user x 50k-item interaction
  matrix is 5 billion entries dense, but typically <0.1% non-zero. Every algorithm that touches the
  interaction matrix must work with scipy sparse matrices; converting to dense is a correctness bug
  for any non-toy dataset. The `InteractionMatrix` wrapper enforces this — it stores CSR, never
  dense.
- **Cold-start is the hard problem — surface it, don't hide it.** Pure collaborative filtering
  cannot recommend for users or items with no interaction history. Content-based and hybrid
  recommenders exist precisely to address this. The architecture should make the cold-start boundary
  explicit: which algorithms handle cold-start users (content-based, two-tower with side features),
  which handle cold-start items (content-based), and which handle neither (pure CF). Surface this
  in the algorithm registry metadata and the generated catalog descriptions.
- **The `[recommend]` extra must stay lean.** `implicit` (MIT, C++/Cython extensions, no torch
  dependency) is deliberately the only library in the extra. Do not pull `surprise` (less
  maintained, pure Python, slower — sklearn's own SVD/NMF cover the explicit-rating path),
  `LensKit` (heavy transitive deps, overlapping surface), or `RecBole` (torch-only, overlaps with
  our own torch-optional deep-recommender path). If a user needs a library we don't wrap, that's
  what the `custom_code` node is for.
- **Evaluation must include system-level metrics, not just accuracy.** A recommender that always
  recommends the 10 most popular items will score well on precision@k and hit rate on most
  datasets. Coverage, diversity, and novelty are the metrics that reveal this failure mode. Ship
  them alongside the ranking metrics from the start, not as an afterthought.
- **Determinism is harder than it looks for matrix factorization.** ALS and BPR are iterative
  algorithms with random initialization; `implicit`'s `random_state` must be verified to produce
  bitwise-identical results across runs. If it doesn't (e.g., due to parallel execution), document
  the tolerance and assert on the equivalence gate with an appropriate epsilon on scores (but exact
  match on the ranked item order for top-k with well-separated scores on the test fixture).
- **Two-tower models are the bridge to production — but production serving is out of scope.** The
  two-tower architecture (separate user/item encoders, ANN retrieval) is how real-world
  recommendation systems work at scale. This epic ships the offline training + evaluation surface;
  online serving (FAISS indices, model export, real-time feature stores) is a future epic.
  Document this boundary explicitly.
- **Don't drift into adjacent/future epics.** Online learning / bandit algorithms, reinforcement-
  learning-based recommendation, real-time model serving, A/B testing infrastructure, knowledge-
  graph-based recommendation, session-based / sequential recommendation, and graph neural networks
  are their own future epics. A few will be natural follow-ons (sequential recommendation extends
  two-tower with attention; bandits extend evaluation with online regret), but they are out of
  scope here.
- **License hygiene still applies.** scipy/sklearn/pandas/numpy (BSD), implicit (MIT), torch
  (BSD) are all clean. The bans: **surprise** is BSD-3 but less maintained and overlaps sklearn's
  surface — don't pull it. **RecBole** is MIT but torch-only and heavy — our own torch path
  covers the deep-recommender surface. No GPL deps.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
