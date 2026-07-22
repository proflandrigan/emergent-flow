# Bug Hunt Report: `emergentflow/` (branch `issue-fixes-v1`)

## Summary
- Scope reviewed: a fresh pass over `issue-fixes-v1`'s full diff against `main` (~4,900
  insertions, 61 files -- the #91-#95 feature set and its follow-up PR #90 fix commit), plus
  a full local run of `ruff check`, `ruff format --check`, `mypy emergentflow`, and `uv run
  pytest` used as automated lead generators. Manually re-reviewed the four PR #90 fixes
  already applied (`apply_mutation`'s cascade, `separateOverlappingNodes`, `pasteNodes`,
  `CodePanel`'s line-splitter) for correctness, and read through the newer files not named in
  the prior 2026-07-21 PR #90 report's explicit scope (`eval/score.py`, `eval/judge.py`,
  `codegen/inspect.py`, `llm_prompt_from_file.py`, `llm_prompt.py`'s wired-template ports,
  `server/service.py`'s `/inspect` route, `StepsPanel.tsx`, `SelectionToolbar.tsx`,
  `ChatComposer.tsx`, `toReactFlow.ts`/`IRToolbar.tsx`/`Palette.tsx`).
- Confirmed findings: 1 (Low), fixed in this session.
- One-paragraph assessment: the four fixes from the prior PR #90 bug hunt hold up under
  re-review -- the cascade/de-overlap/paste logic and the tag-aware line splitter are all
  correct on the traces I checked, including repeated-paste and multi-collision scenarios.
  The new #92/#93/#95 feature code (wired prompt templates, deterministic/LLM-judge scorers,
  the step-trace inspector) is sound; nothing there produced a demonstrable defect. The one
  confirmed finding surfaced from running the full test suite as a lead generator: a
  `DeprecationWarning` fired by `emergentflow/ml/summaries.py`'s `summarize_outlier` when
  summarizing a fitted `OneClassSVM` -- an existing, pre-PR helper unrelated to the #91-#95
  work, whose `float()` call on an array-shaped attribute will turn into a hard `TypeError`
  once NumPy removes the deprecated implicit-scalar-conversion path.

## Findings

### Low — `summarize_outlier`'s `float(offset)` will hard-crash on `OneClassSVM` once NumPy drops the deprecated array→scalar conversion
- **Location:** `emergentflow/ml/summaries.py:108-111` (pre-fix)
- **Class:** Outdated/deprecated API usage
- **Confidence:** Confirmed
- **Description:** `summarize_outlier` is the `summary_builder` registered for four
  `cluster_detect`-archetype estimators (`emergentflow/ml/catalog.py:1217,1239,1257,1274`):
  `IsolationForest`, `LocalOutlierFactor`, `OneClassSVM`, `EllipticEnvelope`. Three of those
  expose `offset_` as a plain Python `float`; `sklearn.svm.OneClassSVM.offset_` is instead a
  NumPy `ndarray` of shape `(1,)`. `float()` on a non-0-d array is deprecated as of NumPy 1.25
  ("Conversion of an array with ndim > 0 to a scalar is deprecated, and will error in future")
  and today only warns -- but the warning explicitly states it becomes a `TypeError` in a
  future NumPy release. The file's own `summarize_regressor` (line 50-55) already guards the
  structurally identical case for `intercept_` with an explicit `ndim == 0` branch; `offset_`
  was left unguarded, an inconsistency within the same module rather than a deliberate choice.
- **Evidence / Reproduction:**
  1. Direct repro:
     ```python
     import numpy as np, warnings
     from sklearn.svm import OneClassSVM
     X = np.random.RandomState(0).randn(20, 3)
     est = OneClassSVM().fit(X)
     print(est.offset_.ndim)          # 1 -- not a scalar
     with warnings.catch_warnings(record=True) as w:
         warnings.simplefilter("always")
         float(est.offset_)
         print(w[0].category, w[0].message)
     # DeprecationWarning: Conversion of an array with ndim > 0 to a scalar is
     # deprecated, and will error in future. ...
     ```
  2. The unpatched code path fires the *identical* warning during a full `uv run pytest`
     run, pinned to the exact source line:
     `emergentflow/ml/summaries.py:110: DeprecationWarning: Conversion of an array with
     ndim > 0 to a scalar is deprecated...`, raised by
     `tests/test_ml_equivalence_matrix.py::test_cluster_detect_archetype_summary_equivalence[OneClassSVM]`.
     It was the only first-party (non-third-party-library) warning in the entire suite's
     84 warnings, confirming the project's own code -- not a dependency -- triggers it.
  3. The existing `test_summarize_outlier` unit test never caught this because it only
     exercises `IsolationForest` (plain-float `offset_`); only the cross-estimator
     equivalence-matrix test happened to also cover `OneClassSVM`.
- **Impact:** Silent today (a warning, tests still pass); on a NumPy upgrade that promotes
  this deprecation to an error (already flagged "will error in future" as of NumPy 1.25,
  currently on 2.3.5 in this project's lockfile), every call to `ef.ml.summarize`/
  `fit_estimator` structural-summary code for a fitted `OneClassSVM` node would raise
  `TypeError` instead of returning a summary -- breaking that node type's inspector output
  and any downstream code relying on `ef.ml.summarize`.
- **Remediation (applied):** Replaced `float(offset)` with `float(np.asarray(offset).item())`,
  which extracts the single scalar for both the plain-float case (other three estimators) and
  the shape-`(1,)` array case (`OneClassSVM`) without triggering the deprecated conversion.
  Added `tests/test_ml_summaries.py::test_summarize_outlier_array_valued_offset_no_deprecation_warning`,
  which fits a real `OneClassSVM`, asserts `offset_.ndim == 1` (so the test can't silently stop
  covering the array-shaped case), wraps the call in
  `warnings.simplefilter("error", DeprecationWarning)`, and asserts it does not raise. Full
  `ruff check`, `ruff format --check`, `mypy emergentflow`, and the targeted test file are
  green; the full `uv run pytest` suite was re-run for confirmation.

## Notes & unverified leads (optional)
- `ui/src/canvas/layout.ts`'s `layeredLayout` (the new "Tidy layout" action, issue #91) does not
  exclude `notes.markdown` note nodes from the layered grid placement, and `tidyLayout()` in
  `graphStore.ts` never re-runs `separateOverlappingNodes`/preserves note-to-anchor adjacency.
  Notes have no incoming/outgoing `Edge`s, so they all land in layer 0 and get repositioned
  away from whatever they were annotating; `NoteAnchorOverlay`'s leader-line still draws
  correctly (it recomputes from live positions, and `layeredLayout`'s row-counter guarantees no
  exact overlap), so nothing crashes or renders incorrectly -- this is a plausible UX
  regression (a note visually detaches from its subject after "Tidy layout"), not a
  demonstrated defect. Would need product input on whether notes are meant to participate in
  auto-layout at all before treating this as a bug.

## Coverage & limitations
- Did not re-review families/files outside this branch's diff (e.g., `emergentflow/stats/`,
  `emergentflow/recommend/`, `emergentflow/timeseries/`) -- out of scope for an issue-fixes
  branch hunt.
- Did not run the UI test suite (`npm test`) or `eslint`/`tsc` in this pass; relied on manual
  trace-through for the TypeScript files reviewed, plus the fact the prior PR #90 report
  already ran and passed those gates on the same diff.
- The `summarize_outlier` fix is scoped to the one confirmed defect; did not audit every other
  `float(...)`/`int(...)` call site across `emergentflow/` for the same NumPy-array-coercion
  pattern beyond this file's `summaries.py` (where the neighboring `intercept_`/`inertia_`
  handling was checked and found already correct or not applicable).
