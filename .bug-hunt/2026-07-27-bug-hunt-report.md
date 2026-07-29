# Bug Hunt Report: explode_lists / encode_lists (feature/explode-encode-lists-two-tower)

## Summary
- Scope reviewed: the three commits new to this branch vs `main` — `emergentflow/clean/__init__.py`
  (`explode_lists`, `encode_lists`, `_coerce_labels`), their reference nodes
  (`emergentflow/nodes/examples/explode_lists.py`, `encode_lists.py`), and the two-tower node
  registration fix. The pre-existing `_fit_two_tower_impl` in `emergentflow/recommend/catalog.py`
  was not touched by this branch and was only skimmed, not audited.
- Confirmed findings: 1 High, 1 Medium.
- Overall assessment: the new `explode_lists`/`encode_lists` ops are otherwise well-covered by
  their test suite, but both confirmed bugs sit exactly in the intended use case (recommender
  interaction data with possibly-missing per-element values, and feature frames combined with
  pre-existing numeric columns) and both fail silently — no exception, no warning, just wrong or
  missing data downstream.

## Findings

### High — `explode_lists(..., drop_empty=True)` silently drops rows with a genuine `None`/NaN list element, not just rows from empty lists
- **Location:** `emergentflow/clean/__init__.py:222-227` (the `explode_lists` function body,
  specifically the `result.dropna(subset=columns, how="all")` call)
- **Class:** Logic error / silent data loss
- **Confidence:** Confirmed
- **Description:** The docstring and `docs/recommender-data-prep.md:135-137` both state that
  `drop_empty=True` (the default) only drops the placeholder row produced when a list is empty
  or the cell is missing. In fact, `dropna(subset=columns, how="all")` cannot distinguish "this
  row came from an empty list" from "this row came from a real list element that happens to be
  `None`/NaN" — both look like a NaN cell after `explode`. When only one column is exploded (the
  common case), `how="all"` on a single-column subset degenerates to "drop if NaN at all," so any
  legitimate `None` inside an otherwise non-empty list silently vanishes along with its row's
  other column values.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.clean import explode_lists

  df = pd.DataFrame({"u": [1, 2], "items": [["a", None], ["c"]]})
  print(explode_lists(df, columns=["items"], drop_empty=True))
  ```
  Actual output:
  ```
     u items
  0  1     a
  1  2     c
  ```
  The `None` element of `["a", None]` — a real element the caller put in the list, not an empty
  list — is exploded to its own row and then dropped along with it, with no error or warning.
  Expected (per the docstring's stated contract, "empty lists / missing *cells*" only): a row
  `(u=1, items=None)` should either be kept as a NaN row or the API should document that
  per-element `None`s inside populated lists are also treated as empty — the current code
  does the latter silently, contradicting its own docstring and `docs/recommender-data-prep.md`.
- **Impact:** This is the exact shape of data `explode_lists` was built for — e.g. the
  `ratings`/`item_ids` aligned-explode pattern in `docs/recommender-data-prep.md` and
  `tests/test_two_tower_data_prep_example.py`. A ratings list with one missing rating
  (`[5, None, 4]`) silently loses that interaction row under the default `drop_empty=True`,
  with no indication anything was dropped — leading to under-counted interactions and a
  recommender fit on silently incomplete data.
- **Remediation:** Distinguish "row is an empty-list placeholder" from "row is a real NaN
  element" before dropping. One approach: detect empty-list/missing cells *before* exploding
  (e.g. mark which original rows had an empty/missing list per column) and drop only those
  post-explode, rather than relying on `dropna` over the exploded result, e.g.:
  ```python
  is_empty = df[columns].apply(
      lambda col: col.map(lambda v: v is None or (isinstance(v, float) and pd.isna(v)) or v == []),
  )
  really_empty_mask = is_empty.all(axis=1)  # rows to drop, computed pre-explode
  df = df[~really_empty_mask] if drop_empty else df
  result = df.explode(columns if len(columns) > 1 else columns[0], ignore_index=False)
  ```
  (adjust to keep the "keep the row if any exploded column bore a real element" semantics used
  today for the multi-column case). At minimum, the docstring/docs should be corrected if the
  current silent-drop-of-None-elements behavior is intended to stay.

### Medium — `encode_lists` can silently produce duplicate-named output columns when a generated indicator column collides with an existing column
- **Location:** `emergentflow/clean/__init__.py:280-286` (the `pd.DataFrame(encoded, columns=[...])`
  / `pd.concat([base, indicator], axis=1)` construction in `encode_lists`)
- **Class:** API/contract misuse → silent output corruption (duplicate column labels)
- **Confidence:** Confirmed
- **Description:** `encode_lists` names each new indicator column `f"{prefix}_{label}"` and
  concatenates it onto the (unencoded) rest of the frame with no check for a name collision
  against columns already present in `df`. If the frame already has a column that happens to
  share a generated name (very plausible: the two-tower data-prep flow this feature targets
  routinely mixes hand-authored numeric feature columns with `encode_lists` output on the same
  frame, per `docs/recommender-data-prep.md`'s own `popularity` example), the result is a
  DataFrame with two columns sharing the same label.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.clean import encode_lists

  df = pd.DataFrame({"u": [1, 2], "g_rock": [10, 20], "g": [["rock"], ["jazz"]]})
  result = encode_lists(df, column="g")
  print(list(result.columns))          # ['u', 'g_rock', 'g_jazz', 'g_rock']
  print(result.columns.duplicated().any())  # True
  ```
  `result["g_rock"]` now returns a 2-column DataFrame instead of a Series wherever it's
  selected downstream, and the original numeric `g_rock` values are silently shadowed/mixed
  with the newly generated multi-hot column of the same name.
- **Impact:** Any downstream code doing `df["g_rock"]` (feature selection into `fit_two_tower`,
  a later `scale_features`/`select_columns` node, a user's own pandas code) either gets a
  2-column DataFrame where a Series was expected (raising confusing errors far from the actual
  cause) or silently picks up the wrong column depending on pandas' resolution order — no
  exception is raised at the point of the actual defect (`encode_lists` itself).
- **Remediation:** Validate for collisions before concatenating, and raise a clear `ValueError`
  the same way the function already does for an unknown `column`:
  ```python
  indicator_cols = [f"{resolved_prefix}_{cls}" for cls in binarizer.classes_]
  collisions = [c for c in indicator_cols if c in base.columns]
  if collisions:
      raise ValueError(
          f"generated indicator columns {collisions!r} collide with existing columns in the "
          f"input frame; choose a different prefix."
      )
  ```
  placed right before the `pd.concat` call, using `base.columns` (post-drop) so a collision with
  `column` itself (when `drop=True`) isn't flagged spuriously.

## Notes & unverified leads (optional)
- `_coerce_labels` (`emergentflow/clean/__init__.py`) only special-cases `list`/`tuple`/`set`
  cells; a cell holding a `numpy.ndarray` (a common shape for list-typed columns loaded from
  Parquet/Arrow) falls through to `return [value]`, wrapping the unhashable array as a single
  "label." This would raise inside `MultiLabelBinarizer.fit_transform` and get re-labeled as
  "mixed, mutually unsortable types" by the new `except TypeError` handler — a plausible but
  *misleading* error message, not silent data loss. Not promoted to a finding: `encode_lists`'s
  docstring only documents support for Python lists/tuples/sets or separator-split strings, so
  ndarray cells are arguably out of contract, and I did not confirm the exact exception path
  (set-vs-sort code path inside `MultiLabelBinarizer` across sklearn versions) with a live repro.
- Did not audit `emergentflow/recommend/catalog.py::_fit_two_tower_impl` (the actual two-tower
  model fit/id-matching logic) — it is pre-existing code this branch did not modify beyond
  docstrings, so it was out of scope for a hunt focused on the branch's new work.

## Coverage & limitations
- Reviewed: `emergentflow/clean/__init__.py` new functions, both new reference nodes
  (`explode_lists.py`, `encode_lists.py`), the two-tower node registration change, and the
  branch's new/changed tests.
- Not reviewed in depth: `emergentflow/recommend/catalog.py`'s two-tower model internals, the UI
  catalog JSON diff (generated artifact, not hand-written logic), and the codegen string-template
  paths for the two new nodes (`ctx.in_var`/`ctx.out_var` wiring) — these looked like the
  established, already-battle-tested pattern used by every other reference node and weren't
  singled out for repro attempts.
