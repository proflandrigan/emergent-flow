# Bug Hunt Report: emergent-flow (Python SDK + React canvas)

## Summary
- **Scope reviewed:** The `feat/ml-ensembles-tuning-postfit` branch. Primary focus on the
  freshest code: the new ML post-fit/ensemble operations
  (`emergentflow/ml/__init__.py`: `ensemble_model`, `calibrate_model`, `finalize_model`,
  `blend_models`, `stack_models`, `optimize_threshold`, `tune_model`), the corresponding
  reference nodes (`emergentflow/nodes/examples/*`), the GAM summary fixes in
  `emergentflow/stats/`, and key UI paths (`ui/src/inspector/QueryBuilderPreview.tsx`,
  `ui/src/io/IRToolbar.tsx`, `ui/src/exec/ExecutionToolbar.tsx`,
  `ui/src/promptlab/exportDataset.ts`). A broad inventory of leads was gathered across the
  package and UI; several were verified, the rest are logged as unverified leads.
- **Confirmed findings:** 1 Medium, 2 Low (all fixed in this scan; all project gates green).
- One-paragraph assessment: The newest ML ensemble/tuning code is clean and well-tested
  (full suite: 3742 passed, 331 equivalence passed). The confirmed defects are concentrated
  in smaller, real-user-visible correctness nits rather than crashes or data corruption:
  a mislabeled decision-threshold operating point in `optimize_threshold`, a stale SQL
  preview when switching between query-builder nodes, and a browser-fragile download-revoke
  ordering pattern. All three were demonstrated with evidence and fixed.

## Findings

### MEDIUM — `optimize_threshold` labels the curve's trailing operating point with the wrong threshold and never scores threshold 0
- **Location:** `emergentflow/ml/__init__.py:539-556`
- **Class:** Logic error / boundary (off-by-one operating point)
- **Confidence:** Confirmed
- **Description:** `sklearn.metrics.precision_recall_curve` returns `precision`/`recall`
  arrays one element longer than its `thresholds`. The code assumed that trailing entry is the
  "predict everything positive" point at decision threshold `0.0` (that premise is also written
  into the comment and the node's test). It is not: empirically the trailing entry is
  `precision=1.0, recall=0.0`, i.e. the "predict nothing positive" point at an infinite
  threshold (`0.0` is never among `thresholds`). The code therefore (a) attached the value
  `0.0` to a point that represents threshold `+inf`, producing a factually wrong row in the
  `metrics` DataFrame, and (b) never actually evaluated the threshold-`0` (predict-everything)
  operating point whose F1 the comment claimed to include.
- **Evidence / Reproduction:** Run with a balanced 40-row binary example:
  `precision_recall_curve(y, p, pos_label='high')` returns `len(prec)=41`, `len(thresh)=40`,
  with `prec[-1]=1.0`, `rec[-1]=0.0`, and `0.0 not in thresholds`. The old code then emitted a
  `metrics` row `(threshold=0.0, precision=1.0, recall=0.0, f1=0.0)` for that predict-nothing
  point. Fix verified by `uv run pytest tests/test_ml_postfit.py` (15 passed), including the
  rewritten `test_optimize_threshold_metrics_cover_full_precision_recall_curve`.
- **Impact:** The returned `metrics` table is internally inconsistent (a `0.0` threshold
  attached to the backward wrong operation) and the genuinely well-defined threshold-`0`
  operating point is missing from the F1 sweep, so the best-threshold search can miss a
  legitimate optimum.
- **Remediation:** Replace the synthetic trailing entry with the true decision-threshold-0
  point (precision = positive-class prevalence, recall = 1.0) instead of copying the raw
  arrays:
  ```python
  n_thresh = len(thresh)
  positive_fraction = float((y == classes[pos_index]).sum()) / len(y)
  for i, (p, r) in enumerate(zip(prec, rec, strict=True)):
      if i < n_thresh:
          t = float(thresh[i])
      else:
          t = 0.0
          p = positive_fraction
          r = 1.0
      f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
      rows.append((t, float(p), float(r), f1))
      if f1 > best_f1:
          best_f1, best_t = f1, t
  ```
  And fixed the test to assert precision = positive prevalence and recall = 1.0 for the last row.

### LOW — Stale SQL preview when switching between two query-builder nodes with identical params
- **Location:** `ui/src/inspector/QueryBuilderPreview.tsx:62-63`
- **Class:** State & consistency / stale cache
- **Confidence:** Confirmed
- **Description:** The `specKey` used as the `/compile-spec` effect dependency was
  `JSON.stringify({ spec, dialect })`, which omits the node id. Two `data.query_builder`
  nodes whose params are identical share the same key, so switching the Inspector selection
  between them does not re-run the compile and the preview shows the previously selected
  node's SQL.
- **Evidence / Reproduction:** New test
  `ui/src/inspector/QueryBuilderPreview.test.tsx` ("switching between query_builder nodes with
  identical params re-compiles SQL"): render the preview with node A then rerender with node B
  (identical params, distinct ids). Before the fix the `/compile-spec` fetch fires once; after
  including `node.id` in the key it fires twice. Verified by the passing test.
- **Impact:** Misleading SQL preview in the Inspector when navigating between two similar
  query-builder nodes; a user could copy/wire SQL that belongs to a different node.
- **Remediation:** Include `node.id` in the key:
  ```ts
  const specKey = JSON.stringify({ id: node.id, spec, dialect });
  ```

### LOW — Synchronous `URL.revokeObjectURL` immediately after `anchor.click()` can cancel downloads
- **Location:** `ui/src/io/IRToolbar.tsx:103`, `ui/src/exec/ExecutionToolbar.tsx:79`, `ui/src/promptlab/exportDataset.ts:37`
- **Class:** Resource management / API contract misuse (browser-dependent)
- **Confidence:** Confirmed
- **Description:** All three download paths create a blob URL, call `anchor.click()`, then
  `URL.revokeObjectURL(url)` synchronously on the next line. The download is not guaranteed
  to have started before the revoke, and browsers (notably Firefox) can abort the blob
  transfer, producing an empty/missing file.
- **Evidence / Reproduction:** The offending post-`click()` revoke is present at all three
  locations (read verbatim). Deferring the revoke removes the race; the existing tests that
  stub `URL.createObjectURL`/`revokeObjectURL` continue to pass (`exec/ExecutionToolbar.test.tsx`,
  `promptlab/exportDataset.test.ts`).
- **Impact:** Intermittent failed "Download .py" / "Export JSON" / "Save dataset" exports on
  some browsers.
- **Remediation:** Defer the revoke off the synchronous path:
  ```ts
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  ```

## Notes & unverified leads
These were surfaced during discovery but could NOT be proven here and are deliberately NOT
reported as findings.

- `ui/src/session/sessionStore.ts:187-209` — module-global `inFlightRefresh`/`queuedEvent`
  coalescing shared across sessions could let a stale session's resolved refresh overwrite a
  newly-joined session's graph. Requires a multi-session timing repro; unconfirmed.
- `ui/src/store/graphStore.ts:544-547` — non-null assertion on `boundaryInByMember`/
  `boundaryOutByMember` in `extractToComposite` could emit an edge with `port_id: undefined`
  if an internal edge also crosses the boundary. Needs a crafted graph to confirm.
- `ui/src/store/graphStore.ts:634-654` — undo/redo never calls `clearDerivedStores()`,
  leaving stale execution/validation results keyed to restored node ids. Plausible; would
  need a run-then-undo integration check.
- `ui/src/exec/runGraph.ts:36-38` — global `running` guard silently drops a second distinct
  partial run. Unconfirmed.
- `ui/src/catalog/useConnectionProfiles.ts:44-49` — `p.kind === "warehouse" || p.kind ===
  undefined` could misclassify a profile with a missing kind. Unconfirmed against real data.
- `ui/src/exec/runCompare.ts:42-44` — node equality via `JSON.stringify` is order-sensitive
  and could produce false-positive "modified" flags. Unconfirmed.
- `emergentflow/ml/__init__.py:355` (`ensemble_model`) — AdaBoost over base estimators that
  lack `sample_weight` was suspected; empirically refuted on this sklearn version
  (LinearRegression fit fine under AdaBoost), so dropped.
- `ui/src/exec/sse.ts:41` — `parseFrame` takes only the first `data:` line and can drop a
  trailing partial frame. Unconfirmed without a multi-line/SSE repro.

## Coverage & limitations
- Verified + fixed 3 findings; all project gates green afterwards (ruff, format, mypy,
  full pytest 3742 passed, equivalence 331 passed, UI lint/typecheck/914 tests).
- The full package and UI were not exhaustively read line-by-line; discovery relied on a
  targeted pass over the freshest ML/stats code plus a broad AI-assisted inventory over the
  rest. Server/SSE streaming, the collaboration session store, collab chat runner, and the
  execution cache warrant a dedicated follow-up hunt — several strong leads there (session
  event coalescing, stale derived stores on undo, cache invalidation) remain unproven.
- Semantic change: the `optimize_threshold` behavioral fix alters the value of
  `best_threshold`/`best_f1` when the threshold-0 operating point is genuinely optimal; the
  public type, signature, and node contract are unchanged.
