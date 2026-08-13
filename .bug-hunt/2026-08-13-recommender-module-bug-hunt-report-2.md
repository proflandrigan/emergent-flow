# Bug Hunt Report: emergentflow.recommend

## Summary
- Scope reviewed: the recommender-systems family — `emergentflow/recommend/` (metrics, interactions,
  sequences, transforms, models, registry, catalog, and the `__init__.py` wrapper seam:
  `fit`/`recommend`/`similar_items`/`fit_sequence`/`fit_two_tower`/`evaluate`/`compare`/
  `hybrid_weighted`/`hybrid_switching`/`prepare_interactions`/`temporal_split`/`random_split`/
  `save_model`/`load_model`).
- Confirmed findings: 1 Medium (metrics)
- Overall assessment: The recommender arcade is well-structured and carefully reviewed — the
  interaction-matrix construction, split helpers, hybrid blend/split layers, SVD/NMF/co-occurrence/
  two-tower/GRU4Rec fit+recommend loops were all checked and correct. The one genuine defect found
  is in the NDCG metric: it normalizes against an ideal DCG that can exceed the number of positions
  the recommended list actually occupies, so a short-but-perfect recommendation is unfairly
  under-scored. This inflates false confidence in algorithms that return fewer than `k` items and
  corrupts the `mean_ndcg_at_k` rankings emitted by `evaluate`/`compare`.

## Findings

### Medium — NDCG@k under-scores a perfect, short recommendation list
- **Location:** `emergentflow/recommend/metrics.py:44` (`_ndcg_at_k`)
- **Class:** Boundary / off-by-something: ideal-DCG denominator unbounded by the scored positions
- **Confidence:** Confirmed
- **Description:** `_ndcg_at_k` computes the ideal discounted cumulative gain (IDCG) as the sum of
  `min(len(relevant), k)` discount weights, but the actual DCG only scores
  `min(k, len(recommended))` positions (the recommended list is often shorter than k — e.g. when
  `exclude_known=True` leaves few unseen items, or the user has interacted with most of the
  catalog). When `len(recommended) < len(relevant)`, the IDCG counts more relevant slots than the
  list could ever fill, so even a recommendation where every returned item is relevant scores
  strictly below 1.0. That silently deflates `mean_ndcg_at_k` for lists that happen to be short,
  biasing `compare()`'s NDCG-based ranking and `evaluate()`'s per-user scores.
- **Evidence / Reproduction:**
  ```python
  from emergentflow.recommend.metrics import _ndcg_at_k
  _ndcg_at_k([1], {1, 2, 3}, 10)      # perfect: only item recommended IS relevant
  # before fix -> 0.46927872602275644  (should be 1.0)
  # after fix  -> 1.0
  _ndcg_at_k([1, 2], {1, 2, 3, 4, 5}, 10)  # perfect, 2 relevant returned
  # before fix -> < 1.0  (should be 1.0); after fix -> 1.0
  ```
  Regression tests added in `tests/test_recommend_metrics.py`:
  `test_ndcg_perfect_short_list_is_one`, `test_ndcg_matches_full_length_when_list_fills_k`,
  `test_ndcg_empty_and_zero_k_return_zero`.
- **Impact:** Any user measuring NDCG@k where the recommender can return fewer than `k` relevant
  items gets an artificially low score; system-level rankings (`compare`) are distorted for
  short-result recommenders. No crash, but silently-wrong metric output on a realistic path.
- **Remediation:** Cap the IDCG at the number of positions actually scored — the URL-legal,
  standard formula — instead of the bare relevant count:
  ```python
  n_positions = min(k, len(recommended))
  dcg = sum((1.0 / math.log2(i + 2)) for i in range(n_positions) if recommended[i] in relevant)
  n_rel = min(len(relevant), n_positions)   # was: min(len(relevant), k)
  if n_rel == 0:
      return 0.0
  idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
  return dcg / idcg
  ```
  When `len(recommended) >= k` the result is byte-for-byte identical to the old behaviour, so
  existing full-length evaluations are unchanged (verified by the regression test
  `test_ndcg_matches_full_length_when_list_fills_k`).

## Notes & unverified leads
None advanced to findings. Leads checked and resolved as correct code (not reported):
- `_prepare_interactions` fixed-point min-interaction filter loop (dedup + count recompute) — correct.
- `weight_interactions_by_recency` tz-aware/naive mixing — only reachable via an explicit
  tz-mismatched `reference_time`; no evidence path in the SDK, left unproven.
- `_average_precision_at_k` / `_auc_at_k` denominators and `topk.index()` handling — correct.
- `temporal_split` uses `n_test = max(1, round(...))` so a single-interaction user always keeps one
  test row — intended and documented.
- GRU4Rec padding/`ignore_index` and two-tower negative-sampling complement logic — correct.
- `evaluate`'s system-level metrics (coverage/diversity/novelty) divide-by-zero guards — correct.

## Coverage & limitations
- Platforms: `tests/test_recommend*.py` full suite (304 passed, 53 skipped), the recommend
  equivalence-matrix gate (11 passed, 5 skipped), `ruff check`, `ruff format --check`, and `mypy`
  on `emergentflow/recommend` all green.
- Deep-model tests (torch-backed) were skipped in this environment (torch absent); their code was
  reviewed statically but not exercised live.
- Not covered this pass: node codegen/execute equivalence for every recommend node
  (covered by the equivalence-matrix gate, which passed), and the canvas `ui/` layer.