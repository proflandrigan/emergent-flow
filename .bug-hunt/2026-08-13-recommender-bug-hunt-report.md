# Bug Hunt Report: emergentflow.recommend

## Summary
- Scope reviewed: the full recommender tooling family — `emergentflow/recommend/` (`__init__.py`,
  `interactions.py`, `metrics.py`, `sequences.py`, `transforms.py`, `models.py`, `registry.py`,
  `generator.py`, and `catalog.py` wrapped around it), plus the reference recommend nodes in
  `emergentflow/nodes/examples/recommend_*.py`. Optional-dependency algorithms (ALS/BPR via
  `implicit`, deep models via `torch`, embedding via `sentence-transformers`) were read for
  correctness but only the base-dependency paths could be executed; tests requiring those extras
  were skipped (53 in the run).
- Confirmed findings: 1 Medium, 1 Low
- Overall assessment: The recommender family is well-tested (290 recommendations tests pass) and
  the base-dependency algorithms are sound on their main paths. Two real correctness defects
  surfaced: a system-level evaluation metric (`coverage`) can exceed 1.0 — an impossible value
  for a fraction — when the test catalog is a strict subset of the recommender's catalog (the
  norm after a train/test split); and a recency transform crashes with an untyped `TypeError`
  on timezone-mismatched inputs instead of the family's typed error. Both are fixed, with
  regression tests.

## Findings

### Medium — `evaluate` coverage metric can exceed 1.0
- **Location:** `emergentflow/recommend/__init__.py:478`
- **Class:** Logic error / metric definition violation
- **Confidence:** Confirmed
- **Description:** `evaluate(...)`'s system-level `coverage` metric is computed as
  `len(recommended_union) / test_interactions.n_items`. The recommended items come from the
  recommender's **full** catalog (the training side), which is typically a strict superset of the
  items present in the held-out `test` InteractionMatrix. Dividing a union that includes
  train-only items by the smaller test catalog size yields a fraction **greater than 1** — an
  impossible value for coverage (a fraction of a catalog by definition). The existing
  `test_system_coverage` test only passed because its fixture happened to have every recommended
  item present in the test catalog, masking the defect.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, emergentflow as ef
  df = pd.DataFrame({"u":[1,1,1,2,2,3,3,3,4], "i":["a","b","c","a","d","b","c","d","e"]})
  train, test = ef.recommend.random_split(df, user_col="u", item_col="i", seed=0)
  m = ef.recommend.fit(train, algorithm="popularity")
  ev = ef.recommend.evaluate(m, test, k=2, metrics=["coverage"])
  print(ev.aggregate["coverage"])   # -> 1.5  (train catalog {a,b,c,d,e} / test n_items=2)
  ```
  `train.item_ids == ['a','b','c','d','e']` (5 items), `test.item_ids == ['b','d']` (2 items);
  the recommended union spans all 5 train items, so `5 / 2 = 2.5` and here `1.5`. Correct value
  (fraction of test-catalog items in any top-k) is `1.0`.
- **Impact:** `map_at_k`/`coverage` rows produced by `evaluate` and `compare` (which calls
  `evaluate`) can report a coverage value > 1.0, silently corrupting the reported evaluation
  and any downstream comparison/viz (e.g. `viz_plot_coverage_vs_accuracy`). Users would see
  nonsense ("125% coverage").
- **Remediation:** Restrict the recommended-item union to the test catalog before dividing, so
  coverage stays bounded to `[0, 1]`:
  ```python
  if test_users and test_interactions.n_items > 0:
      test_item_set = set(test_interactions.item_ids)
      recommended_union: set[Any] = set()
      for items in recs_by_user.values():
          recommended_union.update(items[:k])
      aggregate["coverage"] = (
          len(recommended_union & test_item_set) / test_interactions.n_items
      )
  ```
  Applied. Regression test: `test_system_coverage_never_exceeds_one_when_catalog_skewed`
  (`tests/test_recommend_evaluate.py`).

### Low — recency weighting crashes with untyped `TypeError` on timezone mismatch
- **Location:** `emergentflow/recommend/transforms.py:144`
- **Class:** Error handling / typed-error contract violation
- **Confidence:** Confirmed
- **Description:** `weight_interactions_by_recency` computes `(computed_reference - timestamps)`.
  When `reference_time` is timezone-aware but the data's `timestamp_col` is tz-naive — or
  vice-versa — pandas raises a bare `TypeError: Cannot subtract tz-naive and tz-aware datetime-like
  objects`, escaping the typed-error contract the whole function (and the recommend family)
  follows. The function already raises the typed `InvalidRecommenderParamsError` for NaT / null /
  unparseable inputs, so a mixed-timezone input is an inconsistency in that exact guarding path.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, emergentflow as ef
  df = pd.DataFrame({"t": pd.to_datetime(["2020-01-01","2020-01-02","2020-01-03"]),
                     "user":[1,1,1], "item":["a","b","c"]})
  ef.recommend.weight_interactions_by_recency(
      df, timestamp_col="t", user_col="user", item_col="item",
      reference_time="2020-01-04T00:00:00+00:00")
  # -> TypeError: Cannot subtract tz-naive and tz-aware datetime-like objects.
  ```
  Raw untyped crash on a plausible input combination.
- **Impact:** A user passing tz-aware reference data against naive timestamps (both accepted by
  the API) gets an opaque pandas `TypeError` rather than a clear diagram/node error, and any
  graph that middlewares this would fail confusingly. Low severity because it requires the
  mismatch to occur.
- **Remediation:** Guard the mismatch up-front and raise the typed error, matching the existing
  NaT guard immediately above it:
  ```python
  if (computed_reference.tzinfo is None) != (timestamps.dt.tz is None):
      ref_kind = "naive" if computed_reference.tzinfo is None else "timezone-aware"
      data_kind = "naive" if timestamps.dt.tz is None else "timezone-aware"
      raise InvalidRecommenderParamsError(
          "reference_time is " + ref_kind + " but timestamp_col contains "
          + data_kind + " timestamps; recency cannot be computed across mixed timezones.")
  ```
  Applied. Regression test: `test_tz_mismatched_reference_raises_typed_error`
  (`tests/test_recommend_transforms.py`).

## Notes & unverified leads
- **Two-tower negative sampling (`catalog.py:2447`)** — `rng.choice(complement, size=K, replace=True)`
  samples with replacement; for a small complement this can yield duplicate negatives, and in the
  documented degenerate fallback (a user who has interacted with every item) negatives are drawn
  from the full catalog and may include the user's own positive items. This is a training-quality
  issue, not a crash, and the code documents the fallback as unavoidable. Not promoted to a
  finding because it requires torch to reproduce and the effect is degraded training, not wrong
  output. Would need a torch environment + convergence comparison to confirm impact.
- **`svd_cf` vs `nmf_cf` single-dimension handling** — `svd_cf` raises a typed error for
  `min(shape) < 2` while `nmf_cf` proceeds with `n_components=1`; a quick check showed NMF succeeds
  on a 1×3 matrix, so this is an intentional divergence, not a bug. Refuted.
- **Deep-model paths (NCF/two-tower/GRU4Rec)** and ALS/BPR — read but not executed (torch/implicit
  absent). Their rank/shortlist and padding loops looked internally consistent; deeper review in a
  torch-capable environment is recommended.

## Coverage & limitations
- Reviewed all of the recommend family's source and its reference nodes; executed the
  base-dependency paths and the full `tests/test_recommend_*.py` suite (290 passed, 53 skipped).
- Did NOT run the torch-backed (`ncf`, `two_tower`, `gru4rec`, declarative deep models) or
  `implicit`-backed (`als`, `bpr`) algorithms, nor the `sentence-transformers` embedding path,
  because those extras are not installed here. Those File→line traces for coverage/novelty and the
  blend functions were reviewed by inspection only.
- The fix to `coverage` changes a previously-silent-wrong numeric output; no downstream test
  depended on the broken >1 behavior (verified by running the full suite).