# Bug Hunt Report: Recommender Module (package + UI)

## Summary
- Scope reviewed: the `emergentflow.recommend` package (`catalog.py`, `__init__.py`, `metrics.py`,
  `interactions.py`, `models.py`, `sequences.py`, `transforms.py`, `registry.py`, `generator.py`),
  the recommender reference nodes (`emergentflow/nodes/examples/recommend_*.py`), the recommend
  consumer in `emergentflow/viz/__init__.py`, and the UI integration
  (`ui/src/inspector/RecommendationsPanel.tsx`, `ConfigForm.tsx`, `Inspector.tsx`). Torch/implicit
  gated paths (NCF, two-tower, ALS, BPR, GRU4Rec) were read statically but not executed (deps not
  installed; their tests skip).
- Confirmed findings: 1 High, 1 Medium.
- Overall assessment: The module is well-structured and the ADR-0002 equivalence invariant is held
  by construction across the wiring. Two real defects surfaced and were reproduced: an empty
  `RecommendationResult` carries no columns and crashes downstream consumers (`evaluate`) with
  `KeyError('user_id')`, and `temporal_split` uses banker's-rounding so small users silently
  contribute nothing to the test set. Both were fixed with minimal, targeted changes and covered
  by new regression tests; the full suite (3758 tests), equivalence gate, mypy, ruff, and the UI
  subset all pass.

## Findings

### HIGH — Empty `RecommendationResult` carries no columns, crashing `ef.recommend.evaluate`
- **Location:** `emergentflow/recommend/models.py:64`
- **Class:** Null / missing value / contract violation
- **Confidence:** Confirmed
- **Description:** Every `recommend_fn` builds its result via `pd.DataFrame(rows)`. When an
  algorithm produces zero recommendations — most realistically with `exclude_known=True` while
  every requested user has already interacted with every item — `pd.DataFrame([])` yields an
  `(0, 0)` frame with **no columns**. Downstream consumers index these columns unconditionally,
  so `ef.recommend.evaluate` (line 425) crashes with `KeyError: 'user_id'` when `recommend()`
  returns zero rows for *all* test users. The `RecommendationResult` docstring promises columns
  `user_id, item_id, rank, score`, so this is a contract violation, not just a crash.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.recommend import prepare_interactions, fit, recommend, evaluate
  df = pd.DataFrame({"user":["u1","u2","u1","u2"],"item":["a","b","b","a"]})
  ints = prepare_interactions(df, user_col="user", item_col="item", implicit=True)
  rec = fit(ints, algorithm="popularity", params={})
  r = recommend(rec, user_ids=["u1","u2"], n=10, exclude_known=True)
  # => r.recommendations.shape == (0, 0), columns == []   (no user_id column)
  evaluate(rec, ints, k=10)   # => KeyError: 'user_id'
  ```
  Observed traceback in `recommend/__init__.py:425` → `IndexError.get_loc` → `KeyError: 'user_id'`.
- **Impact:** Any user who has rated every catalog item breaks the entire evaluation run (and any
  downstream consumer of `RecommendationResult`, including the hybrid blend/split layers and the
  canvas payload path) with a raw `KeyError` instead of returning an empty, well-formed result.
- **Remediation:** Normalize an empty frame in `RecommendationResult.__post_init__` so every result
  exposes the documented schema:
  ```python
  def __post_init__(self) -> None:
      if self.recommendations.empty:
          self.recommendations = pd.DataFrame(columns=["user_id", "item_id", "rank", "score"])
  ```
  Re-run the repro: `evaluate` now returns an all-zeros `EvalResult` instead of crashing. Covered by
  `tests/test_recommend_baseline_catalog.py::test_empty_recommendation_result_has_canonical_columns`.

### MEDIUM — `temporal_split` drops a user's newest interaction from test due to banker's rounding
- **Location:** `emergentflow/recommend/__init__.py:836`
- **Class:** Boundary / arithmetic (rounding)
- **Confidence:** Confirmed
- **Description:** `n_test = round(len(ordered) * test_ratio)` uses Python's banker's rounding
  (round-half-to-even). For a user whose `count * test_ratio` lands exactly on a half boundary —
  e.g. 2 interactions at `test_ratio=0.25` → `0.5` → rounds **down to 0** — the `else` branch keeps
  the entire group in train and contributes **zero** rows to `test`. The docstring promises "each
  user's last `test_ratio` fraction of interactions goes to test"; instead these small users are
  silently absent from the held-out set, biasing recall/precision toward heavier users.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.recommend import temporal_split
  df = pd.DataFrame({"user":["u1","u1","u2","u2","u2","u2"],
                     "item":["a","b","a","b","c","d"],
                     "ts":[0,1,0,1,2,3]})
  train, test = temporal_split(df, user_col="user", item_col="item",
                               timestamp_col="ts", test_ratio=0.25)
  # Before fix: test.user_ids == ['u2']  (u1's newest interaction 'b' never held out)
  # After fix:   test.user_ids == ['u1','u2'], u1's train row == {'a'}
  ```
- **Impact:** Users with slate interactions (very common in real interaction data) never appear in
  the test matrix, silently shrinking the evaluation set and making ranking metrics unrepresentative
  of small users.
- **Remediation:** Hold out at least the newest interaction for any user who has data:
  ```python
  n_test = max(1, round(len(ordered) * test_ratio))
  test_parts.append(ordered.iloc[-n_test:])
  train_parts.append(ordered.iloc[:-n_test])
  ```
  Existing 5-row/0.4 expectations (`round(2.0)=2`) are unchanged. Covered by
  `tests/test_recommend_interactions.py::test_temporal_split_holds_out_newest_interaction_for_small_users`.

## Notes & unverified leads
- **Recommendation model `n` param is declared but never read by fitters.** Every catalog entry
  lists `n` in `optional_params`/`param_metadata`, but `n` is only consumed by `recommend()`, not by
  `fit()`. Passing `params={"n": ...}` to `fit` is silently accepted and ignored. Harmless/no-op —
  not reported as a finding.
- **`recommend_evaluate` node help text says "all eight" metrics** but `_VALID_EVAL_METRICS` now has
  ten (`mrr_at_k`, `auc_at_k` added). Cosmetic doc/catalog mismatch, no behavioral impact.
- **`random_split` also uses `round()`** but across the whole frame (typically large), so
  banker's-rounding is negligible and there is no per-user starvation — left as-is.
- **GRU4Rec/two-tower/NCF runtime** (torch) could not be executed (torch not installed). Static
  review found forward semantics consistent with training (next-item prediction, dot-product scoring
  matching train loss). GRU4Rec `exclude_known` only filters the truncated window's items, so long
  sessions with items pushed out before the `max_seq_len` window could recall already-seen items;
  unverified because torch is unavailable.

## Coverage & limitations
- Executed paths: baseline/content/collaborative/non-torch (popularity, random, segmented, SVD,
  NMF, co-occurrence, user/item KNN, tfidf, feature_knn, embedding_similarity), interactions,
  sequences, transforms, metrics, evaluate, compare, hybrid blend/split, save/load, nodes, viz
  consumers, UI.
- Not executed (deps absent): torch-backed NCF/two-tower/GRU4Rec and implicit-backed ALS/BPR.
- The full Python suite (3758 passed), `-m equivalence` gate (331 passed), `mypy`, `ruff check`,
  and the UI lint/typecheck/tests all pass after the fixes.