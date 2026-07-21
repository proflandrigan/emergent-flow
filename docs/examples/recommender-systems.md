# Recommender Systems

Emergent Flow's `ef.recommend` family is a dedicated seam for recommender systems — a parallel
to `ef.ml`, not an extension of it. Recommenders consume sparse user-item interaction matrices
and produce ranked item lists, not feature-target DataFrames and point predictions, so the
family gets its own types (`InteractionMatrix`, `FittedRecommender`, `RecommendationResult`,
`EvalResult`) and its own fit/recommend/evaluate seam rather than routing through
`ef.ml.fit_estimator`. This guide walks through preparing interaction data, fitting algorithms
from the curated catalog, generating recommendations, blending recommenders into hybrids, and
evaluating/comparing them with ranking metrics.

## 1. Preparing Interaction Data

Recommenders start from a tidy events/ratings DataFrame — one row per user-item interaction:

```python
import emergentflow as ef
import pandas as pd

interactions_df = pd.DataFrame({
    "user_id": ["u1", "u1", "u1", "u2", "u2", "u3", "u3", "u3", "u3", "u4"],
    "item_id": ["i1", "i2", "i3", "i1", "i4", "i2", "i3", "i4", "i5", "i1"],
    "rating": [5, 3, 4, 4, 5, 2, 5, 3, 4, 3],
})
print(interactions_df)
```

```
  user_id item_id  rating
0      u1      i1       5
1      u1      i2       3
2      u1      i3       4
3      u2      i1       4
4      u2      i4       5
5      u3      i2       2
6      u3      i3       5
7      u3      i4       3
8      u3      i5       4
9      u4      i1       3
```

`ef.recommend.prepare_interactions` turns this into a validated, sparse `InteractionMatrix`. It
de-duplicates repeated `(user, item)` pairs (via `agg`, default `"sum"`), can drop
low-interaction users/items (`min_user_interactions`/`min_item_interactions`,
`cold_start_mode="warn-and-skip"` by default), and never mutates the input frame:

```python
interactions = ef.recommend.prepare_interactions(
    interactions_df, user_col="user_id", item_col="item_id", value_col="rating",
)
print(f"Users: {interactions.n_users}, Items: {interactions.n_items}")
print(f"Matrix shape: {interactions.matrix.shape}")
print(f"User IDs: {interactions.user_ids}")
print(f"Item IDs: {interactions.item_ids}")
```

```
Users: 4, Items: 5
Matrix shape: (4, 5)
User IDs: ['u1', 'u2', 'u3', 'u4']
Item IDs: ['i1', 'i2', 'i3', 'i4', 'i5']
```

`interactions.matrix` is a scipy CSR sparse matrix — it is never densified, even for
inspection. That is load-bearing: a 100k-user x 50k-item matrix is 5 billion entries dense but
typically <0.1% non-zero. `interactions.summary()` gives a tidy, JSON-native view (`n_users`,
`n_items`, `n_interactions`, `density`, `implicit`) for anywhere the raw matrix can't render.

## 2. Fitting a Recommender

`ef.recommend.fit` is the single seam every algorithm in the catalog routes through — pass an
`algorithm` key and (optionally) a `params` dict validated against that algorithm's
required/optional param allow-list:

```python
# Popularity baseline
model = ef.recommend.fit(interactions, algorithm="popularity")
print(f"Algorithm: {model.algorithm}")   # "popularity"

# SVD (matrix-factorization collaborative filtering)
model = ef.recommend.fit(interactions, algorithm="svd_cf", params={"n_components": 10})

# Item-based KNN (memory-based collaborative filtering)
model = ef.recommend.fit(interactions, algorithm="item_knn_cf", params={"k": 5})
```

`fit` returns a `FittedRecommender` — the one dataclass every archetype rides inside, mirroring
`ef.ml.FittedModel`. Its inspectable fields are `algorithm` (the catalog key), `algorithm_family`
(`"baseline"`, `"content"`, `"collaborative"`, or `"deep"`), `n_users`/`n_items`, and `fit_stats`
(JSON-native training metrics — sparsity, convergence info, etc.). The live model object rides
in `model` but degrades to `{"kind": "unsupported"}` on the result-payload contract, so it never
renders directly.

The curated catalog spans four archetypes:

| Family | Algorithm keys |
| --- | --- |
| Baseline | `random`, `popularity`, `popularity_segmented`, `co_occurrence` |
| Content-based | `tfidf_similarity`, `feature_knn`, `embedding_similarity` |
| Collaborative | `user_knn_cf`, `item_knn_cf`, `svd_cf`, `nmf_cf`, `als`*, `bpr`* |
| Deep | `ncf`†, `two_tower`† |

\* requires the `[recommend]` extra (`implicit`). † requires the optional `torch` dependency.
See [§9](#9-optional-extras) below.

## 3. Getting Recommendations

`ef.recommend.recommend` generates top-N recommendations from a fitted recommender:

```python
result = ef.recommend.recommend(model, user_ids=["u1"], n=5, exclude_known=True)
print(result.recommendations)
```

```
  user_id item_id  rank     score
0      u1      i4     1  0.812345
1      u1      i5     2  0.564321
```

`result.recommendations` is a tidy DataFrame with columns `user_id`, `item_id`, `rank`, `score`
— JSON-native and round-trips through the result-payload contract untouched, unlike
`FittedRecommender.model`. `exclude_known=True` (the default) drops items already present in the
recommender's own training interactions for that user — the standard recommender-systems
convention.

```python
# Recommend for every user the recommender was fit on
result = ef.recommend.recommend(model, user_ids=None, n=10, exclude_known=True)
```

## 4. Finding Similar Items

For algorithms that support item-item similarity (e.g. `co_occurrence`), `similar_items` returns
the N most similar items to each given item:

```python
similar = ef.recommend.similar_items(model, item_ids=["i1"], n=5)
print(similar)
```

Calling `similar_items` on an algorithm whose registry entry has no `similar_items_fn` (most
collaborative/content algorithms) raises `InvalidRecommenderParamsError`.

## 5. Hybrid Recommenders

Two composition layers blend already-fitted recommenders — neither is a new algorithm family,
each just calls the existing `recommend()` wrapper per input recommender and combines the
results.

### Weighted / rank-fusion / cascade blending

`hybrid_weighted` combines two or more recommenders' outputs under one of three strategies:
`"weighted_sum"` (per-item scores scaled by weight and summed), `"rank_fusion"` (reciprocal-rank
fusion — scale-agnostic across algorithms with incomparable raw scores), or `"cascade"`
(recommenders tried in descending-weight priority order, filling `n` slots without duplicates):

```python
model_pop = ef.recommend.fit(interactions, algorithm="popularity")
model_svd = ef.recommend.fit(interactions, algorithm="svd_cf")

result = ef.recommend.hybrid_weighted(
    recommenders=[model_pop, model_svd],
    weights=[0.3, 0.7],
    user_ids=["u1"], n=5,
)
```

### Cold-start switching

`hybrid_switching` routes each user to one of exactly two fitted recommenders by their known
interaction count in a reference `InteractionMatrix` — the classic cold-start pattern. It takes
the interactions matrix directly (only to look up interaction counts; nothing is refit) plus a
required `cold_start_threshold`:

```python
result = ef.recommend.hybrid_switching(
    recommenders=[model_pop, model_svd],   # [cold_start_recommender, warm_recommender]
    interactions=interactions,
    cold_start_threshold=3,   # users with < 3 known interactions get model_pop
    user_ids=["u1"], n=5,
)
```

## 6. Evaluation

Splitting is done on the raw tidy DataFrame, not on an already-built `InteractionMatrix` — both
split functions build their own train/test `InteractionMatrix` pair internally:

```python
# Random row split (no timestamp needed)
train, test = ef.recommend.random_split(
    interactions_df, user_col="user_id", item_col="item_id", value_col="rating",
    test_ratio=0.2, seed=42,
)

# Or split by per-user recency (requires a timestamp column in the source frame)
# train, test = ef.recommend.temporal_split(
#     interactions_df, user_col="user_id", item_col="item_id", value_col="rating",
#     timestamp_col="event_time", test_ratio=0.2,
# )

# Fit on train, evaluate on test
model = ef.recommend.fit(train, algorithm="svd_cf")
result = ef.recommend.evaluate(
    model, test, k=10,
    metrics=["precision_at_k", "recall_at_k", "ndcg_at_k", "hit_rate", "coverage", "diversity"],
)
print(result.aggregate)
```

```
{
    'mean_precision_at_k': 0.15,
    'mean_recall_at_k': 0.42,
    'mean_ndcg_at_k': 0.31,
    'hit_rate': 0.67,
    'coverage': 0.6,
    'diversity': 0.28,
}
```

`evaluate` scores a fitted recommender's top-`k` recommendations against held-out interactions.
`metrics` selects a subset of `{"precision_at_k", "recall_at_k", "ndcg_at_k", "map_at_k",
"hit_rate", "coverage", "diversity", "novelty"}` — `None` (the default) computes all eight.
Five are per-user (aggregated as `mean_<metric>`, or `hit_rate`/`map_at_k` directly); three are
system-level, computed once across all users and reported only in `aggregate`: `coverage`
(fraction of the catalog appearing in any user's top-k), `diversity` (1 − mean pairwise cosine
similarity of users' top-k item sets), and `novelty` (mean `-log2(popularity)` of recommended
items). `result.per_user` is the tidy per-user frame backing the per-user metrics.

## 7. Comparing Algorithms

`compare` evaluates multiple already-fitted recommenders against the same held-out test set and
ranks them — the recommend-family analog to `ef.ml.compare_models`. Every candidate must already
be fitted; `compare` does not fit anything itself except an automatic popularity baseline:

```python
model_pop = ef.recommend.fit(train, algorithm="popularity")
model_item_knn = ef.recommend.fit(train, algorithm="item_knn_cf")
model_svd = ef.recommend.fit(train, algorithm="svd_cf")

comparison = ef.recommend.compare(
    test,
    recommenders=[model_pop, model_item_knn, model_svd],
    k=10,
)
print(comparison)
```

```
     algorithm  is_baseline  mean_precision_at_k  mean_recall_at_k  mean_ndcg_at_k  hit_rate  map_at_k  coverage  diversity  novelty
0       svd_cf        False                 0.18              0.47            0.34      0.71      0.22       0.6       0.31      2.1
1  item_knn_cf        False                 0.16              0.44            0.29      0.68      0.19       0.5       0.27      1.9
2   popularity        False                 0.12              0.35            0.21      0.55      0.14       0.4       0.10      0.8
```

The result is a tidy DataFrame: one row per recommender, an `algorithm` column, an `is_baseline`
bool column, and one column per evaluation metric — sorted by `mean_ndcg_at_k` descending (the
strongest recommender by ranking quality is always first). If none of `recommenders` is already
a `"popularity"` algorithm, `compare` automatically fits one on `test` and appends it with
`is_baseline=True` as a rough contextual reference point — note it is trained on `test` itself,
not the same training data as the other recommenders, so it isn't a strictly apples-to-apples
baseline.

## 8. Visualization

```python
# Metric comparison bar chart (one bar group per recommender, one color per metric)
plot = ef.viz.plot_metric_comparison(comparison)

# Coverage vs. accuracy scatter — the classic accuracy/diversity trade-off
plot = ef.viz.plot_coverage_vs_accuracy(comparison)

# Precision-recall trade-off curve, sweeping k=1..k_max for one fitted recommender
plot = ef.viz.plot_precision_recall_curve(model, test, k_max=50)

# Long-tail histogram: recommendation frequency vs. item popularity rank (log scale)
plot = ef.viz.plot_popularity_distribution(model, interactions, n=10)
```

## 9. Optional Extras

Two algorithm families are gated behind optional dependencies — calling `fit` with a gated
algorithm whose extra isn't installed raises a typed `MissingOptionalDependencyError`, never an
opaque `ImportError`:

- **`emergentflow[recommend]`** (the `implicit` library): `als` (Alternating Least Squares) and
  `bpr` (Bayesian Personalized Ranking) — implicit-feedback matrix factorization.
- **`torch`** (optional, same dependency the declarative PyTorch seam uses): `ncf` (Neural
  Collaborative Filtering) and `two_tower` — deep recommenders.

```python
# pip install 'emergentflow[recommend]'
model = ef.recommend.fit(interactions, algorithm="als", params={"factors": 64, "iterations": 15})
```

Two-tower is the only algorithm that consumes both item-feature and user-feature side inputs, so
it has its own dedicated wrapper (`ef.recommend.fit_two_tower`) alongside `fit`, rather than
widening the shared `Fitter` signature for every other algorithm.

## 10. In the Canvas

> **In the Canvas:** Add a `prepare_interactions` node to convert your DataFrame into an
> InteractionMatrix, then connect to a `recommend_fit` node. Wire the fitted model to
> `recommend_recommend` for recommendations or `recommend_evaluate` for metrics. Use
> `recommend_compare` to benchmark multiple algorithms side by side. See
> [Canvas UI Guide](canvas-ui-guide.md).
