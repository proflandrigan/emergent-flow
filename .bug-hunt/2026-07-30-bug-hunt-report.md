# Bug Hunt Report: PR #109 — first-class outlier detection (`detect_outliers`, `outlier_summary`, `outlier_detect` archetype)

## Summary

- **Scope reviewed:** the full `main...outlier-detection` diff (24 files, +1919/-86). Read line
  by line: `emergentflow/clean/outliers.py`, the `outlier_summary` addition to
  `emergentflow/stats/eda.py`, `fit_and_detect` / `fit_estimator` / `fit_pipeline` /
  `_resolve_estimator_and_kwargs` in `emergentflow/ml/__init__.py`, the four re-archetyped
  catalog entries in `emergentflow/ml/catalog.py`, `ml/registry.py`, `ml/generator.py`, and all
  three new node files plus the narrowed `cluster_detect` node. Skimmed only: the regenerated
  `ui/src/generated/catalog.json` and the two `.ambr` snapshots (verified in sync by re-running
  `scripts/export_ui_contracts.py`).
- **Confirmed findings:** 1 High, 3 Medium.
- **Gates:** `ruff check`, `ruff format --check`, `mypy emergentflow` (308 files), the full
  `pytest` suite (3376 passed / 62 skipped), `export_ui_contracts.py` (artifacts in sync), and
  `check_ui_boundary.py` all pass on this branch. Every finding below is behavioral and escapes
  the existing gates.

The PR's central claim — that `ef.stats.outlier_summary`'s reported cut is by construction the
cut `ef.clean.detect_outliers` applies — **holds**. I fuzzed the two ops against each other
across all five methods and thirteen frame shapes (NaN-bearing, constant, zero-IQR, single-row,
empty, all-NaN, integer, nullable `Int64`, near-int64-max, mixed-dtype, duplicate-index) and
found zero disagreements. ADR-0002 equivalence also holds: I wrote 19 additional
`execute`-vs-emitted-code cases across all three new nodes (including `drop`, `combine="all"`,
and every method) and all pass. The defects are elsewhere: the **`outlier_score` column** is
silently wrong on multi-column frames whose fence collapses, `fit_and_detect` labels
`LocalOutlierFactor` in the one way sklearn explicitly documents you must not, `drop=True`
refuses frames it has no reason to refuse, and the archetype move breaks previously-saved graphs
without a version bump or a validation error.

---

## Findings

### High — `outlier_score` reports an unrelated column's benign score for a row that IS an outlier

- **Location:** `emergentflow/clean/outliers.py:261` (`result[score_column] = scores.max(axis=1)`),
  root cause at `emergentflow/clean/outliers.py:162-166` (`_deviation`)
- **Class:** Logic error / silently wrong result (NaN masking under `max`)
- **Confidence:** Confirmed

**Description.** `_deviation` returns `NaN` for a column whose fence has zero width on the
relevant side — a documented, deliberate choice ("no meaningful score"). But `detect_outliers`
then collapses the per-column scores with `scores.max(axis=1)`, and pandas' `max` **skips NaN by
default**. So when column *A* flags a row but cannot score it, and column *B* scores the same row
a benign `0.39`, the row is published as `is_outlier=True, outlier_score=0.39`.

That is not "no score" — it is a *confident, finite, small* score that contradicts the flag and
violates the module's own stated contract (`_deviation`: "`1.0` exactly *on* either fence, and
`> 1.0` outside it — the same meaning for every method"). The PR advertises exactly the workflow
this breaks: *"so the existing `clean.filter_rows` node can subset on it directly — no
`custom_code` escape hatch."*

A zero-width fence is not exotic. It occurs whenever ≥50% of a column's values are identical
(`modified_zscore`, MAD = 0) or the interquartile range is 0 (`iqr`) — the normal shape of
latency, count, retry, and status columns.

**Evidence / Reproduction.** The PR's own invariant test
(`tests/test_clean_outliers.py:205`, `test_outlier_score_above_one_iff_flagged`) asserts
`outlier_score > 1.0 ⟺ is_outlier` over non-NaN scores — but only on a **single-column** frame.
Extend it verbatim to two columns and it fails:

```python
@pytest.mark.parametrize(
    ("method", "threshold"),
    [("zscore", 2.0), ("modified_zscore", 3.0), ("iqr", 1.5), ("quantile", 0.05), ("percent", 0.1)],
)
def test_outlier_score_above_one_iff_flagged_two_columns(method, threshold):
    df = pd.DataFrame({"x": [10.0] * 8 + [900.0, 1200.0],      # collapsed fence
                       "y": [i / 9 for i in range(10)]})       # benign ramp
    result = detect_outliers(df, method=method, threshold=threshold)
    scored = result["outlier_score"].notna()
    assert ((result.loc[scored, "outlier_score"] > 1.0) == result.loc[scored, "is_outlier"]).all()
```

```
2 failed, 3 passed
FAILED ...[modified_zscore-3.0]
FAILED ...[iqr-1.5]

        x         y  is_outlier  outlier_score
0    10.0  0.000000       False       0.500000   <- inlier, scores 0.50
...
7    10.0  0.777778       False       0.277778
8   900.0  0.888889        True       0.388889   <- 90x outlier, scores 0.39
9  1200.0  1.000000        True       0.500000   <- 120x outlier, scores 0.50
```

Row 9 is 120× the column median and is correctly flagged, yet scores **exactly the same as
inlier row 0**. Sorting by `outlier_score` is meaningless, and `filter_rows` on
`outlier_score > 1.0` returns **zero rows** while `is_outlier` says two.

**Impact.** Any canvas graph that follows `clean.detect_outliers` with a `clean.filter_rows` on
`outlier_score` — the flow the PR body recommends — silently drops the strongest outliers on any
multi-column frame containing a low-variance column. No error, no warning; the wrong rows just
survive. Sorting descending by `outlier_score` to triage "the worst offenders" returns inliers.

**Remediation.** A value strictly outside a zero-width fence is infinitely many fence
half-widths away; `inf` is the mathematical limit and restores the documented contract. In
`_deviation` (`emergentflow/clean/outliers.py:162`):

```python
    for side, width in ((values > centre, upper - centre), (values < centre, centre - lower)):
        if width > 0:
            deviation[side] = (values[side] - centre).abs() / width
        elif width == 0:                       # collapsed fence: strictly outside == infinitely far
            deviation[side] = float("inf")
    deviation[values == centre] = 0.0
```

I applied exactly this patch and re-ran: the two-column invariant test above goes **5 passed**,
and `tests/test_clean_outliers.py` + `tests/test_stats_outlier_summary.py` go 110 passed with a
single expected failure — `test_outlier_score_is_nan_when_the_fence_has_no_width:212`, the test
that codifies the behavior being corrected. Rename it to
`test_outlier_score_is_inf_when_the_fence_has_no_width` and assert
`np.isinf(result["outlier_score"].iloc[-1])`. Update the `_deviation` docstring's NaN paragraph
to say NaN now means only "the value itself is missing." (Working tree was restored afterwards;
no changes are left on disk.)

*Minimal alternative, if NaN semantics must be preserved:* make the reduction NaN-propagating for
columns that flagged — `score[(flags & scores.isna()).any(axis=1)] = float("nan")` after the
`max`. That stops the false-confidence score but still leaves the strongest outliers unreachable
by a numeric filter, so `inf` is the better fix.

---

### Medium — `fit_and_detect` labels the training frame with `LocalOutlierFactor(novelty=True)`, the one usage sklearn documents you must not

- **Location:** `emergentflow/ml/__init__.py:1214-1219` (`fit_and_detect`), curated default at
  `emergentflow/ml/catalog.py:1240-1243`
- **Class:** API / contract misuse (documented precondition violated)
- **Confidence:** Confirmed

**Description.** `fit_and_detect` "labels the SAME frame it fit on" and prefers `.predict(X)`.
The curated `LocalOutlierFactor` spec sets `novelty=True` as a `KwargSpec` default, and
`_resolve_estimator_and_kwargs` (`emergentflow/ml/__init__.py:427-450`) applies curated defaults
unconditionally — so `hasattr(est, "predict")` is `True` and `est.predict(X_train)` is what runs.
sklearn's own docstring for that parameter:

> Set `novelty` to True if you want to use LocalOutlierFactor for novelty detection. **In this
> case be aware that you should only use predict, decision_function and score_samples on new
> unseen data and not on the training set**; and note that the results obtained this way may
> differ from the standard LOF results.

The `fit_and_detect` docstring also claims it falls "back to `.fit_predict(X)` for
`LocalOutlierFactor` with `novelty=False`" — that branch is **unreachable** for every registered
estimator under the curated defaults.

**Evidence / Reproduction.**

```python
rng = np.random.default_rng(1)
df = pd.DataFrame(np.vstack([rng.normal(size=(40, 2)),
                             rng.normal(loc=6, scale=.3, size=(15, 2))]), columns=["a", "b"])
model, lab = ef.ml.fit_and_detect(df, estimator="LocalOutlierFactor")
```

```
curated LOF config novelty              : True   (KwargSpec default=True)
ef.ml.fit_and_detect          n_outliers: 17
sklearn's standard LOF result n_outliers: 18
rows where they disagree                : [16]
   row 16: fit_and_detect=+1  standard LOF=-1   point=[-0.378  2.043]
```

Both alternatives reproduce sklearn's standard result exactly:

```
ef.ml.fit_and_detect(..., params={"novelty": False})   -> 18 outliers  (hasattr(est,'predict') is False)
np.where(est.negative_outlier_factor_ < est.offset_, -1, 1) -> 18 outliers, identical to standard LOF
```

**Impact.** `ml.outlier_detect` with `LocalOutlierFactor` — one of only four estimators the new
node offers — returns training-set labels that silently disagree with standard LOF. The cause is
self-scoring: with `novelty=True`, `predict` treats each training point as unseen, so its
`kneighbors` lookup finds the point itself at distance 0 and inflates its local density. Points
near the decision boundary get misclassified as inliers. No error is raised, and the disagreement
is data-dependent (I found none on 3 of 4 synthetic frames I tried), so it will not reproduce
reliably enough for a user to notice.

**Remediation.** Keep the curated `novelty=True` (cross-frame `apply_estimator` predict depends
on it) and use LOF's fit-time attributes for the training frame, which *are* the standard LOF
result. In `fit_and_detect`:

```python
    est = model.estimator
    X = df[model.feature_names]
    nof = getattr(est, "negative_outlier_factor_", None)
    if nof is not None:
        # LocalOutlierFactor: .predict() on the training set is explicitly disallowed by sklearn
        # when novelty=True (self-scoring inflates local density). The fit-time attributes ARE
        # the standard LOF labels for the fitted frame.
        labels = np.where(nof < est.offset_, -1, 1)
    elif hasattr(est, "predict"):
        labels = est.predict(X)
    elif hasattr(est, "fit_predict"):
        labels = est.fit_predict(X)
    else:
        raise ValueError(f"{model.estimator_type} exposes neither predict nor fit_predict.")
```

I verified `np.where(nof < est.offset_, -1, 1)` is element-wise identical to
`LocalOutlierFactor(n_neighbors=20).fit_predict(df)` on the frame above. Then correct the
docstring's `novelty=False` claim, and add a case to
`tests/test_ml_outlier_detect_catalog.py` asserting
`fit_and_detect(df, estimator="LocalOutlierFactor")["outlier"]` equals
`LocalOutlierFactor(**curated_kwargs_without_novelty).fit_predict(X)`.

*Note:* this same `hasattr(est, "predict")` ordering exists on `main` in `fit_and_label`, so the
behavior is inherited rather than introduced. It is in scope here because the PR moves LOF into a
new function whose entire stated purpose is labeling the fitted frame, and whose docstring makes
a claim about the fallback that is false for the shipped configuration.

---

### Medium — `drop=True` raises `ColumnCollisionError` for columns it never adds

- **Location:** `emergentflow/clean/outliers.py:231-236`
- **Class:** Control flow / wrong validation order
- **Confidence:** Confirmed

**Description.** The collision guard runs before the `drop` branch and unconditionally rejects a
frame that already carries `flag_column`/`score_column`. But `detect_outliers`' own docstring
says `drop=True` "returns only the non-outlier rows **and omits both added columns**" — and the
code agrees (`emergentflow/clean/outliers.py:257-258` returns `df.loc[~is_outlier].copy()`, adding
nothing). There is nothing to collide with, so the guard rejects a call it would have handled
correctly.

**Evidence / Reproduction.**

```python
df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 99.0], "is_outlier": [False] * 4})
ef.clean.detect_outliers(df, columns=["a"], drop=True)
```

```
RAISED: ColumnCollisionError detect_outliers would overwrite existing column(s) ['is_outlier'];
        choose different flag_column/score_column names.
```

**Impact.** Breaks the natural two-node canvas flow the PR enables: a first
`clean.detect_outliers` (inspect the flags and scores), then a second with `drop=True` to cut the
rows. The second node fails on a frame the first node produced, and the error message advises a
fix ("choose different flag_column/score_column names") that is irrelevant to what the user is
doing. Also blocks re-running the node on any frame that already carries an `is_outlier` column
from an upstream source.

**Remediation.** Guard only the path that actually writes the columns. In
`emergentflow/clean/outliers.py`, replace the unconditional check with:

```python
    if not drop:
        collisions = [c for c in (flag_column, score_column) if c in df.columns]
        if collisions:
            raise ColumnCollisionError(
                f"detect_outliers would overwrite existing column(s) {collisions!r}; "
                "choose different flag_column/score_column names."
            )
```

`tests/test_clean_outliers.py:117` (`test_detect_outliers_collision_raises`) does not pass
`drop`, so it continues to pass unchanged; add a companion asserting
`detect_outliers(df, columns=["a"], drop=True)` succeeds and returns only the `a`/`is_outlier`
columns of the inlier rows.

---

### Medium — re-archetyping four estimators breaks previously-saved graphs; `ef.validate` passes and `ClusterDetect.version` is not bumped

- **Location:** `emergentflow/nodes/examples/cluster_detect.py:48` (`version = 1`, unchanged),
  `emergentflow/ml/catalog.py:1209/1229/1252/1270` (`archetype="cluster_detect"` →
  `"outlier_detect"`)
- **Class:** State & consistency / contract versioning
- **Confidence:** Confirmed

**Description.** Moving `IsolationForest`, `LocalOutlierFactor`, `OneClassSVM`, and
`EllipticEnvelope` out of `cluster_detect` is the intended change, and `fit_and_label` correctly
rejects them. But any graph saved before this PR with an `ml.cluster_detect` node holding one of
those four estimator keys is now invalid, and nothing detects it until execution:

- `ClusterDetect.version` stays `1` even though the node's `estimator` param `choices` shrank by
  four entries. CLAUDE.md: *"Per-node `version` (a contract version) is distinct from
  `Graph.schema_version` (the wire format) — bump `version` on any codegen/param change."*
- `ef.validate(graph)` does **not** flag the now-illegal param value. The check exists —
  `NodeDefinition.validate_node` → `_check_hints` → `hints.choices` at
  `emergentflow/nodes/contract.py:399` — but `validate_node` has **no caller anywhere in
  `emergentflow/`**; a repo-wide grep finds it only in `tests/`.
- `codegen` still happily emits `ef.ml.fit_and_label(frame, estimator='IsolationForest', ...)`,
  so an exported script fails at *runtime* rather than at compile time.

**Evidence / Reproduction.**

```python
node = ClusterDetect().instantiate(estimator="IsolationForest", features=["x", "y"])
```

```
node.type    : ml.cluster_detect
node.version : 1
validate() issues: only 'required_input_unconnected' -- the stale estimator is NOT reported
execute RAISED: ValueError : 'IsolationForest' is not a cluster_detect-archetype estimator.
codegen still emits it happily:
    model, result = ef.ml.fit_and_label(frame, estimator='IsolationForest', features=['x','y'], params={})
```

```
$ grep -rn "validate_node" --include=*.py . | grep -v .venv
tests/test_node_contract.py:126  (…and 8 more, all in tests/)
```

**Impact.** A user reopening a saved graph sees a canvas that validates green, then fails at run
time on a node they did not touch — with an error naming an archetype, an internal concept the
canvas never surfaces. An already-exported Python script fails the same way at runtime with no
compile-time signal. The blast radius is bounded (four estimators, one node type) and the failure
is at least loud and correctly worded, which is why this is Medium rather than High.

**Remediation.** Three independent steps, cheapest first:

1. Bump `ClusterDetect.version` to `2` in `emergentflow/nodes/examples/cluster_detect.py:48` —
   the param contract changed, which is precisely what the field is for. Regenerate
   `ui/src/generated/catalog.json` via `scripts/export_ui_contracts.py` and refresh
   `tests/__snapshots__/test_catalog.ambr`.
2. Make the failure surface at validate time, not execute time, by wiring the existing
   `NodeDefinition.validate_node` into the graph validation pass. It is dead code today and
   already implements exactly the `choices` check needed; a stale `estimator` would then land as
   a canvas-visible `Diagnostic` on the offending node.
3. Note the break in the PR body / release notes: graphs using those four estimators under
   `ml.cluster_detect` must be re-pointed at the new `ml.outlier_detect` node.

Steps 2 and 3 are the ones that matter for users; step 1 is the convention CLAUDE.md mandates.

---

## Notes & unverified leads

Leads I chased and could **not** substantiate — recorded so no one re-spends the time. None of
these are findings.

- **`detect_outliers` / `outlier_summary` can disagree.** *Refuted.* Fuzzed all five methods ×
  thirteen frame shapes (NaN-bearing, constant, zero-IQR, single-row, two-row, empty, all-NaN,
  int64, nullable `Int64`, near-`2**62`, mixed dtypes with bool + object columns,
  duplicate-index). Zero mismatches between `summary["n_outliers"]` and the count
  `detect_outliers` flags. The shared-seam design holds.
- **ADR-0002 equivalence for the three new nodes.** *Refuted.* Wrote 19 additional
  `execute`-vs-emitted-code cases beyond the PR's own (all five methods, `columns=`,
  `combine="all"`, `drop=True`, and all four estimators for `ml.outlier_detect`). All pass, all
  results `is_inspectable`.
- **Missing golden/equivalence coverage for the new nodes.** *Refuted.* All three do have node
  level equivalence tests (`tests/test_clean_outliers.py:282`,
  `tests/test_stats_outlier_summary.py:175`,
  `tests/test_ml_outlier_detect_catalog.py:112`). My initial grep for a `*_equivalence.py` file
  missed them because they live in the per-node files.
- **`columns=[]` (an explicitly empty list, which a UI column widget may emit) is treated as
  "no columns" rather than the help text's "empty/unset scans all numeric columns".** Real, but
  **pre-existing and repo-wide** — `distribution_summary`, `scale_features`, `describe`, and ~25
  other nodes pass `columns` straight through identically. Not attributable to this PR; worth a
  separate cross-cutting issue if the UI does in fact emit `[]`, which I did not verify.
- **`_deviation`'s boolean-mask assignment misbehaves on a duplicate index.** *Refuted.* Tested
  with `index=[0,0,1,1,2,2,3,3]`; flags, scores, and row alignment are all correct.
- **`evaluate()` on a `task="outlier_detection"` model falls into the classification branch.**
  True, but it raises immediately on `model.target is None` ("missing target column None"), and
  the identical situation already exists for `task="clustering"` on `main`. Pre-existing, not a
  new defect, and it fails loudly.
- **A collapsed fence produces `NaN` bounds that are not valid JSON when `outlier_summary` is
  serialized to the canvas.** Not chased to a conclusion — `distribution_summary` already emits
  `NaN` the same way, so any problem here is pre-existing. Confirming it would mean driving the
  `/execute` route with an all-NaN column and inspecting the response body.

## Resolution

All four findings were fixed on the `outlier-detection` branch after this hunt. Each original
reproduction was re-run against the fixed code:

| # | Fix | Verification |
|---|---|---|
| 1 | `_deviation` emits `inf` (not `NaN`) for a zero-width fence side | Both outliers now score `inf`, sort to the top, and `outlier_score > 1.0` selects exactly the flagged rows |
| 2 | `fit_and_detect` reads LOF's `negative_outlier_factor_ < offset_` instead of calling `.predict` on the fitted frame | 18 outliers vs standard LOF's 18 — element-wise identical, previously 17 |
| 3 | Collision guard moved behind `if not drop` | `detect_outliers(df_with_is_outlier, drop=True)` succeeds |
| 4 | `ClusterDetect.version` 1 → 2; `validate` now checks param values | A stale `IsolationForest` surfaces as a `param_invalid` `Diagnostic`, and `compile_to_code` raises `GraphValidationError` instead of emitting a script that fails at runtime |

Two adjustments the fixes forced, both worth noting:

- **A latent bug in the newly-activated code.** Wiring the param check into `validate` surfaced
  that `_check_hints` compared a *list-valued* param against `choices` as a whole. For a
  multi-select like `ml.compare_models`' `estimators`, `choices` enumerates valid **elements**,
  so every non-empty selection was rejected. `_check_hints` now checks list params element-wise.
  This had never fired because `validate_node` had no production caller.
- **Scope of the graph-level check.** `validate_node` also flags missing-required and undeclared
  params. Gating graphs on *those* would break the stated invariant that validation "must NOT
  block building exploratory, half-wired graphs" — a node dropped from the palette and not yet
  configured is a normal transient state, and it broke a collab test that legitimately expects a
  half-built graph to validate clean. `validate` therefore gates on a new narrower
  `NodeDefinition.validate_param_values` (hint violations on params that are present), while
  `validate_node` keeps its full behavior for callers that want it.

Gates after the fixes: `ruff check`, `ruff format --check`, `mypy` (308 files), `pytest`
(**3398 passed** / 62 skipped, up from 3376), `export_ui_contracts.py`, `check_ui_boundary.py`,
plus the UI's `tsc --noEmit`, `eslint` (0 errors), and `vitest` (670 passed).

## Coverage & limitations

- **Not reviewed in depth:** `ui/src/generated/catalog.json` (351 lines of generated diff — I
  verified it is byte-identical to a fresh `scripts/export_ui_contracts.py` run rather than
  reading it) and the two `.ambr` snapshots.
- **Not exercised at all:** the server routes (`/execute`, `/execute/stream`, `/catalog`) with
  the new node types, and the `ConfigForm.tsx` change. All verification was in-process against
  the SDK and node definitions; the one-line `CURATED_PARAM_NODES` addition is consistent with
  its three neighbours but I did not run the canvas.
- **`fit_pipeline` with an `outlier_detect` final step** was read and type-checks, but I did not
  build a repro. `LocalOutlierFactor` inside a `Pipeline` is worth a targeted look: the
  `negative_outlier_factor_` remediation in finding 2 reaches the estimator directly, and the
  pipeline path would need `pipe[-1]`.
- **Reproductions** ran locally in the repo venv (Python 3.13, pandas 2.3.3, scikit-learn 1.9.0)
  against synthetic frames only. The one source edit made during verification
  (the `_deviation` `inf` patch, to prove the remediation) was reverted; `git status` is clean.
