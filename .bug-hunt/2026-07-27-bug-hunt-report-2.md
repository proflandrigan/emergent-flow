# Bug Hunt Report: emergentflow.recommend (recommender-systems suite)

## Summary
- Scope reviewed: `emergentflow/recommend/` in full (`__init__.py` seam functions —
  `fit`/`fit_two_tower`/`recommend`/`similar_items`/`evaluate`/`compare`/`hybrid_weighted`/
  `hybrid_switching`/`prepare_interactions`/`temporal_split`/`random_split`; `catalog.py`'s
  entire algorithm catalog — random, popularity, popularity_segmented, co_occurrence,
  tfidf_similarity, feature_knn, embedding_similarity, user_knn_cf, item_knn_cf, svd_cf,
  nmf_cf, als, bpr, ncf, two_tower; `metrics.py`, `interactions.py`, `models.py`,
  `registry.py`, `generator.py`, `errors.py`), the reference node wrappers in
  `emergentflow/nodes/examples/recommend_*.py`, and the two-tower data-prep path in
  `emergentflow/clean/__init__.py` (`explode_lists`/`encode_lists`). Existing test suite
  (`uv run pytest -k recommend`, 280 passed / 19 skipped — all skips due to the optional
  `implicit` package being absent) was run as a sanity baseline before hunting. This report
  supersedes/extends `2026-07-27-bug-hunt-report.md` (an earlier, narrower hunt scoped to
  just this branch's `explode_lists`/`encode_lists` diff) — see the re-verification note
  under Findings below for what changed.
- Confirmed findings: 1 High, 1 Medium.
- Overall assessment: the recommend seam (`fit`/`recommend`/`similar_items`/`evaluate`/
  hybrid composition) is well-factored and its ADR-0002 equivalence holds by construction
  as documented — codegen and execute in every node wrapper route through the identical
  `ef.recommend.*` call with identical arguments. Ranking-metric math in `metrics.py` is
  correct for every degenerate case checked (empty recommended list, empty relevant set,
  k<=0). One new High-severity defect was found in the segmented-popularity baseline's
  cold-start fallback. One previously-reported Medium defect in `ef.clean.encode_lists`
  (column-name collision) is still present and unfixed; a previously-reported High defect in
  `ef.clean.explode_lists` (silent loss of real `None` list elements) has been fixed since
  the earlier report — commit `927dfaa` — and is confirmed resolved below.

## Findings

### High — `popularity_segmented` cold-start fallback collides with an explicit `None` segment
- **Location:** `emergentflow/recommend/catalog.py:421-422` (inside `_recommend_popularity_segmented`)
- **Class:** Logic error / sentinel collision
- **Confidence:** Confirmed
- **Description:** The module comment at `catalog.py:341-345` states the contract plainly:
  *"When a user is missing from user_segments, the fitter falls back to the global ranking."*
  The recommend-time lookup implements this fallback with a single sentinel value:

  ```python
  seg = user_to_segment.get(uid)                    # None if uid is absent
  scores = segment_scores.get(seg, global_scores)    # None if that segment has no entries
  ```

  Both "`uid` is not a key in `user_to_segment`" and "`uid`'s segment is explicitly `None`"
  produce `seg = None` from `dict.get(uid)` — Python's `.get()` cannot distinguish "key
  absent" from "key present with value `None`". If *any* user in the caller's
  `params["user_segments"]` mapping is explicitly assigned segment `None` (a normal way to
  express an "unsegmented"/"unknown" cohort), `_fit_popularity_segmented` computes and stores
  real popularity scores under `segment_scores[None]`. Every subsequent recommend-time lookup
  for a user *entirely absent* from `user_segments` then resolves to `segment_scores[None]`
  — the small explicit-`None`-cohort's scores — instead of `global_scores`, silently
  violating the documented cold-start contract.
- **Evidence / Reproduction:** Ran directly against the current code:

  ```python
  import pandas as pd
  from emergentflow.recommend.interactions import InteractionMatrix
  from emergentflow.recommend import fit, recommend

  rows = [("u1","i1",1.0), ("u1","i2",1.0), ("u2","i3",1.0), ("u2","i3",1.0),
          ("u3","i1",1.0), ("u4","i2",1.0)]
  df = pd.DataFrame(rows, columns=["user_id", "item_id", "value"])
  im = InteractionMatrix.from_dataframe(df, user_col="user_id", item_col="item_id", value_col="value")

  # u1 explicitly assigned segment None; u2 in "A". u3/u4 entirely absent from the map.
  rec = fit(im, algorithm="popularity_segmented",
            params={"segment_col": "segment", "user_segments": {"u1": None, "u2": "A"}})

  print(rec.model["global_scores"])                       # [2. 2. 2.]  (i1, i2, i3)
  print(rec.model["segment_scores"][None])                # [1. 1. 0.]  (u1-only scores)
  print(recommend(rec, user_ids=["u3"], n=3, exclude_known=False).recommendations)
  ```

  Output:
  ```
  global_scores: [2. 2. 2.]
  segment None scores: [1. 1. 0.]
  u3 (missing from segments -> should fallback to GLOBAL):
    user_id item_id  rank  score
  0      u3      i1     1    1.0
  1      u3      i2     2    1.0
  2      u3      i3     3    0.0
  ```

  `u3` is entirely absent from `user_segments` and per the documented contract should receive
  the global ranking `[i1=2, i2=2, i3=2]` (all items tied). Instead it receives `[i1=1, i2=1,
  i3=0]` — exactly `u1`'s solo scores — silently wrong, with `i3` incorrectly ranked last
  instead of tied for first.

  The existing regression test (`tests/test_recommend_baseline_catalog.py::
  test_popularity_segmented_cold_start_fallback`) does not catch this because its
  `user_segments` fixture (`{1: "east", 2: "west"}`) never assigns an explicit `None`
  segment, so `segment_scores` never acquires a `None` key and the `.get(None,
  global_scores)` fallback happens to hit its default by luck rather than by a code path
  that actually distinguishes "absent" from "explicit None".
- **Impact:** Any caller who uses `None` as a legitimate segment value (e.g. "unsegmented" /
  "unknown region" users) gets systematically wrong recommendations for every user who is
  genuinely new/unseen — they silently receive that small `None`-cohort's popularity ranking
  instead of the catalog-wide ranking the API contract promises. No exception, no warning;
  the caller has no signal anything went wrong. This directly undermines the algorithm's
  advertised cold-start handling (`handles_cold_start_users=True`).
- **Remediation:** Use a lookup that can express "not present" distinctly from "present with
  value `None`", e.g.:

  ```python
  _MISSING = object()
  ...
  seg = user_to_segment.get(uid, _MISSING)
  scores = global_scores if seg is _MISSING else segment_scores.get(seg, global_scores)
  ```

  The same ambiguity exists at fit time in `_fit_popularity_segmented`'s `segment_users
  .setdefault(seg, [])` grouping (lines 362-365) and in the "no `user_segments` supplied"
  default (`user_segments = {uid: None for uid in interactions.user_ids}`, lines 359-360) —
  both currently use `None` to mean "no segment", which collides with a caller's own explicit
  `None` segment value. Fixing only the recommend-time lookup without addressing this shared
  sentinel would leave the ambiguity latent. Add a regression test that assigns an explicit
  `None` segment to one user and asserts a *different, entirely absent* user still gets
  `global_scores`.

### Medium — `encode_lists` can silently produce duplicate-named output columns when a generated indicator column collides with an existing column
- **Location:** `emergentflow/clean/__init__.py:287-294` (the `pd.DataFrame(encoded,
  columns=[...])` / `pd.concat([base, indicator], axis=1)` construction in `encode_lists`)
- **Class:** API/contract misuse → silent output corruption (duplicate column labels)
- **Confidence:** Confirmed (carried over from the earlier `explode_lists`/`encode_lists`-scoped
  hunt and independently re-verified against the current tree; still unfixed)
- **Description:** `encode_lists` names each new indicator column `f"{prefix}_{label}"` and
  concatenates it onto the (unencoded) rest of the frame with no check for a name collision
  against columns already present in `df`. If the frame already has a column that happens to
  share a generated name — plausible in exactly the two-tower data-prep flow this feature
  targets, which routinely mixes hand-authored numeric feature columns with `encode_lists`
  output on the same frame before feeding `ef.recommend.fit_two_tower` — the result is a
  DataFrame with two columns sharing the same label.
- **Evidence / Reproduction (re-run against current `HEAD`, commit `927dfaa`):**
  ```python
  import pandas as pd
  from emergentflow.clean import encode_lists

  df = pd.DataFrame({"u": [1, 2], "g_rock": [10, 20], "g": [["rock"], ["jazz"]]})
  result = encode_lists(df, column="g")
  print(list(result.columns))          # ['u', 'g_rock', 'g_jazz', 'g_rock']
  print(result.columns.duplicated().any())  # True
  ```
  Confirmed output:
  ```
  encode_lists result columns: ['u', 'g_rock', 'g_jazz', 'g_rock']
  duplicated: True
  ```
  `result["g_rock"]` now returns a 2-column DataFrame instead of a Series wherever it's
  selected downstream, and the original numeric `g_rock` values are silently shadowed/mixed
  with the newly generated multi-hot column of the same name.
- **Impact:** Any downstream code doing `df["g_rock"]` (feature selection into
  `fit_two_tower`, a later `scale_features`/`select_columns` node, a user's own pandas code)
  either gets a 2-column DataFrame where a Series was expected (raising confusing errors far
  from the actual cause) or silently picks up the wrong column depending on pandas'
  resolution order — no exception is raised at the point of the actual defect
  (`encode_lists` itself).
- **Remediation:** Validate for collisions before concatenating, and raise a clear
  `ValueError` the same way the function already does for an unknown `column`:
  ```python
  indicator_cols = [f"{resolved_prefix}_{cls}" for cls in binarizer.classes_]
  collisions = [c for c in indicator_cols if c in base.columns]
  if collisions:
      raise ValueError(
          f"generated indicator columns {collisions!r} collide with existing columns in the "
          f"input frame; choose a different prefix."
      )
  ```
  placed right before the `pd.concat` call, using `base.columns` (post-drop) so a collision
  with `column` itself (when `drop=True`) isn't flagged spuriously.

## Re-verified as fixed (not a current finding)
- **`explode_lists(..., drop_empty=True)` silently dropping rows with a genuine `None`/NaN
  list element** — reported as High in the earlier, narrower hunt
  (`2026-07-27-bug-hunt-report.md`). Re-tested against the current tree:
  ```python
  import pandas as pd
  from emergentflow.clean import explode_lists
  df = pd.DataFrame({"u": [1, 2], "items": [["a", None], ["c"]]})
  print(explode_lists(df, columns=["items"], drop_empty=True))
  ```
  now correctly produces:
  ```
     u items
  0  1     a
  1  1  None
  2  2     c
  ```
  i.e. the real `None` element is preserved as its own row rather than being dropped. This
  matches commit `927dfaa` ("fix(clean): preserve real None/NaN elements in explode_lists
  under drop_empty") and `_is_empty_list_cell`'s current pre-explode emptiness check
  (`emergentflow/clean/__init__.py:199-205`), which now distinguishes an empty-list/missing
  *cell* from a real `None` *element* before exploding, exactly as the earlier report's
  remediation suggested. No further action needed here.

## Notes & unverified leads (optional)
- `emergentflow/recommend/catalog.py::_fit_ncf`'s negative-sampling loop (`while neg_count <
  negative_samples and attempts < 20`) can silently under-sample negatives (fewer than
  `negative_samples` per positive) for a user who has interacted with a large fraction of the
  catalog, since it gives up after 20 rejection attempts without a fallback. This is the same
  class of issue the neighboring `_fit_two_tower_impl` was explicitly rewritten to avoid (see
  its comment at `catalog.py:2358-2363`), but unlike the bug above I could not demonstrate
  NCF actually mislabels a known item as negative (it just contributes fewer negatives that
  epoch) — so this is a plausible latent quality issue, not a proven correctness bug, and is
  not reported as a finding. Confirming it would require a statistical simulation (as the
  two-tower comment describes doing) rather than a single deterministic repro.
- `_coerce_labels` (`emergentflow/clean/__init__.py`) only special-cases `list`/`tuple`/`set`
  cells; a cell holding a `numpy.ndarray` (a common shape for list-typed columns loaded from
  Parquet/Arrow) falls through to `return [value]`, wrapping the unhashable array as a single
  "label." This would raise inside `MultiLabelBinarizer.fit_transform` and get re-labeled as
  "mixed, mutually unsortable types" by the `except TypeError` handler — a plausible but
  *misleading* error message, not silent data loss. Not promoted to a finding: `encode_lists`'s
  docstring only documents support for Python lists/tuples/sets or separator-split strings, so
  ndarray cells are arguably out of contract, and I did not confirm the exact exception path
  (set-vs-sort code path inside `MultiLabelBinarizer` across sklearn versions) with a live repro.
- `emergentflow/recommend/interactions.py::_prepare_interactions`'s `cold_start_mode="error"`
  path and `emergentflow/recommend/__init__.py::temporal_split`'s per-user `round()`-based
  test-split sizing were both reviewed for edge-case leakage/off-by-one issues and found to
  match their documented contracts on inspection; not independently stress-tested against
  crafted adversarial inputs given time constraints.

## Coverage & limitations
- The `implicit`-backed algorithms (`als`, `bpr`) could not be exercised at runtime (the
  `implicit` package is not installed in this environment), so their fit/recommend code was
  reviewed by inspection only, not executed.
- `two_tower` and `ncf` (both `torch`-backed) *were* exercised — torch is installed and their
  existing test suites ran and passed.
- Did not review `emergentflow/viz/__init__.py`'s recommend-family plotting code, the
  `/reports` rendering of `EvalResult`/`RecommendationResult`, or the UI-facing catalog
  generator's JSON round-trip beyond a read of `generator.py`.
- Did not fuzz or property-test the metrics/interactions math beyond manual edge-case
  reasoning (empty inputs, k<=0, single-row groups); no defect was found there but this was
  not exhaustive.
