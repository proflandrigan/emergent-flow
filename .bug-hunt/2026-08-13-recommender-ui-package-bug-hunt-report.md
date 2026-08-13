# Bug Hunt Report: Recommender UI & Package (independent sweep, tweak pass)

## Summary
- Scope reviewed: the `emergentflow.recommend` package (`catalog.py`, `__init__.py`, `metrics.py`,
  `models.py`, `interactions.py`, `sequences.py`, `transforms.py`, `registry.py`, `generator.py`,
  `errors.py`) and the recommender UI surface (`ui/src/inspector/RecommendationsPanel.tsx`,
  `ConfigForm.tsx`, `Inspector.tsx`). Torch/implicit-gated deep paths (NCF, two-tower, GRU4Rec) and
  implicit-backed ALS/BPR were read statically but not executed (deps absent; their tests skip).
- Confirmed findings: 1 Medium, 1 Medium.
- Overall assessment: This module has been hunted several times (previous reports fixed an empty
  `RecommendationResult` column crash, a `temporal_split` banker's-rounding test starvation, and an
  NDCG IDCG boundary). Prior passes each found one real defect. This independent tweak pass over the
  same surface surfaced two NEW, previously-unreported failures, both on small-data boundary paths:
  `svd_cf` crashes with an untyped sklearn `ValueError` on any interaction matrix whose smaller
  dimension is 1 (a single-item catalog), and both `random_split` and `temporal_split` can silently
  produce an **empty train half** (or empty test half) on small frames via banker's-rounding, yielding
  a degenerate recomender the caller cannot fit on -- the exact sibling of the earlier
  `temporal_split` fix that was left applied to only one bound. The UI layer came back clean.

## Findings

### MEDIUM — `svd_cf` crashes with an untyped sklearn `ValueError` on a single-dimension interaction matrix
- **Location:** `emergentflow/recommend/catalog.py:1580-1583` (`_fit_svd_cf`)
- **Class:** Boundary / unhandled sklearn error (raw library exception leaking a typed API)
- **Confidence:** Confirmed
- **Description:** `_fit_svd_cf` clamps `n_components` with
  `n_components = max(1, min(n_components, max_components)) if max_components > 0 else 1`. When the
  interaction matrix's smaller dimension is 1 (e.g. a single-item catalog, or a matrix with only one
  user/row), `max_components = min(shape) - 1 = 0`, so the code falls into the `else 1` branch and
  passes `n_components=1` to `TruncatedSVD`. But sklearn's TruncatedSVD requires
  `n_components < min(n_samples, n_features)`, i.e. `1 < 1`, which never holds -- so the fit raises a
  raw `ValueError` instead of the typed `InvalidRecommenderParamsError` every other recommender raises
  for degenerate input. `nmf_cf`, `user_knn_cf`, `item_knn_cf` all handle these shapes fine, so this is
  an inconsistency, not a fundamental matrix limitation.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.recommend import prepare_interactions, fit
  ints = prepare_interactions(pd.DataFrame({"user":["u1","u2"], "item":["a","a"]}), user_col="user", item_col="item")
  fit(ints, algorithm="svd_cf", params={})
  # ValueError: Found array with 1 feature(s) (shape=(2, 1)) while a minimum of 2 is required by TruncatedSVD.
  ```
  Empirically triggered on shapes 1x1, 2x1, 3x1 (any `min(shape)==1`); shapes 1x2, 1x3, 2x2, 2x3 fit
  fine. `nmf_cf` fits 1x1/2x1/3x1 without error.
- **Impact:** Any user fitting `svd_cf` on a single-item (or single-user) interaction matrix -- a
  genuinely reachable small-data input the shared `_prepare_interactions` gate does not reject -- gets
  a raw, confusing sklearn exception through the `@public_op` seam instead of a typed, actionable error.
- **Remediation:** Guard on the actual precondition and raise the family's typed error:
  ```python
  if min(matrix.shape) < 2:
      raise InvalidRecommenderParamsError(
          "algorithm 'svd_cf' requires at least 2 users and 2 items to factorize; "
          f"got shape {matrix.shape}."
      )
  max_components = min(matrix.shape) - 1
  n_components = max(1, min(n_components, max_components))
  ```
  (The `else 1` fallback is removed since that path is now unreachable.) Verified: 2x1 now raises
  `InvalidRecommenderParamsError`; 2x3 still fits. Regression test:
  `tests/test_recommend_collaborative_catalog.py::test_svd_cf_single_dimension_matrix_raises_typed_error`.

### MEDIUM — `random_split` (and the upper bound of `temporal_split`) can silently empty one split half on small frames
- **Location:** `emergentflow/recommend/__init__.py:895-897` (`random_split`); `:844` (`temporal_split`)
- **Class:** Boundary / arithmetic (banker's-rounding half-clamping)
- **Confidence:** Confirmed
- **Description:** Both splits compute `n_test = round(len * test_ratio)` (deterministic data, no
  randomness in `temporal_split`). Banker's round-half-to-even makes this asymmetric and reachable:
  - `random_split`, 1 row at 0.5: `round(0.5)=0` → **empty test**.
  - `random_split`, 2 rows at 0.75: `round(1.5)=2` → **empty train** (worse: you cannot fit on it).
  - `temporal_split`, a 2-event user at 0.75: `max(1, round(1.5)) = 2` → all that user's rows go to
    test, **empty train slice for that user**.
  The earlier `temporal_split` fix added only the `max(1, ...)` lower bound (guarding empty test); the
  upper bound (empty train) was never guarded, and `random_split` still has neither bound. The result
  is a silently degenerate split (fit returns a 0-user recommender; `evaluate` reports all-zero
  metrics) with no error or warning.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.recommend import random_split, temporal_split
  tr, te = random_split(pd.DataFrame({"user":["u1","u1"],"item":["a","b"]}), user_col="user", item_col="item", test_ratio=0.75, seed=0)
  # before fix: tr.n_interactions == 0  (empty train), te.n_interactions == 2
  tr2, te2 = temporal_split(pd.DataFrame({"user":["u1","u1"],"item":["a","b"],"ts":[0,1]}), user_col="user", item_col="item", timestamp_col="ts", test_ratio=0.75)
  # before fix: tr2.n_interactions == 0
  tr1, te1 = random_split(pd.DataFrame({"user":["u1"],"item":["a"]}), user_col="user", item_col="item", test_ratio=0.5, seed=0)
  # before fix: te1.n_interactions == 0  (empty test)
  ```
- **Impact:** Splitting a small interaction frame (a common first step in a tiny-dataset tutorial or
  a filtered/sliced slice) can silently send all data to one half, so the downstream fit is trained on
  nothing or the eval set is empty -- both yield meaningless, all-zero results without any signal.
- **Remediation:** Clamp `n_test` to `[1, n-1]` so both halves stay non-empty whenever there are >= 2
  rows/users, and keep a single-row case in train. For `random_split`:
  ```python
  n_rows = len(df)
  n_test = max(1, min(n_rows - 1, round(n_rows * test_ratio))) if n_rows >= 2 else 0
  ```
  For `temporal_split` (per user group of size `n`):
  ```python
  n = len(ordered)
  n_test = max(1, min(n - 1, round(n * test_ratio))) if n >= 2 else 0
  ```
  Pre-existing expectations are unaffected: 5 rows / 0.4 → `round(2.0)=2` stays 2; the existing
  hold-out-newest test (2 events / 0.25 → `max(1, 0)=1`) stays 1. Verified and covered by
  `tests/test_recommend_interactions.py::test_random_split_never_empties_a_half_for_multiple_rows`
  and `::test_temporal_split_never_empties_a_half_for_a_multi_event_user`.

## Notes & unverified leads
- **`weight_interactions_by_recency` overwrites a pre-existing `value_col`.** If the input frame
  already has a column named `weight` (the default `value_col`), the function silently replaces it
  with the computed decay weights instead of "adding" a column as the docstring implies. It returns a
  copy (does not mutate the input), so this is a silent data-overwrite in the returned frame. Low
  severity / arguably intended; not promoted to a finding because the caller explicitly names
  `value_col` and the docstring's "with an added value_col" is ambiguous about collisions.
- **GRU4Rec `exclude_known`** only excludes items within the truncated `max_seq_len` window, so very
  long sessions can re-recommend items scrolled out of the window. Unverified (torch absent) and
  arguably by design for a session model; not reported.
- **Two-tower auto-selected numeric features** can include a numeric id column if `item_features`/
  `user_features` use raw integer ids (since the fitter selects all numeric columns). Unverified as a
  real defect given the id column is usually a string key; noted for deeper review.

## Coverage & limitations
- Executed: the full `tests/test_recommend*.py` suite (307 passed, 53 skipped), the whole repo suite
  (3764 passed, 103 skipped), the `-m equivalence` ADR-0002 gate (331 passed), `mypy` on
  `emergentflow/recommend`, `ruff check` + `ruff format --check`, the UI `lint`/`typecheck`/`test`
  gates (914 tests), and `check_ui_boundary.py`. All green after the fixes.
- Not executed (deps absent): torch-backed NCF/two-tower/GRU4Rec and implicit-backed ALS/BPR were
  reviewed statically only.
- The recommender UI (`RecommendationsPanel.tsx`, `ConfigForm.tsx`, `Inspector.tsx`) was reviewed and
  is covered by existing UI tests; no UI bug was found.