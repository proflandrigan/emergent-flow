# Bug Hunt Report: PR #156 — feat/data-explorer-pin-to-canvas

## Summary
- Scope reviewed: All 10 files changed in PR #156 — `emergentflow/server/payload.py`, `ui/src/store/execution.ts`, `ui/src/inspector/DataPanel.tsx`, `ui/src/inspector/Inspector.tsx`, `ui/src/canvas/toReactFlow.ts`, `ui/src/canvas/nodes/SnapshotNode.tsx`, `ui/src/canvas/nodes/SnapshotNode.css`, `ui/src/canvas/Canvas.tsx`, `tests/test_payload.py`, and the golden snapshot file. Focused on the new describe-stats logic, the TypeScript contract, and the DataPanel UI component.
- Confirmed findings: 1 Critical, 1 Medium, 1 Low
- The new describe-stats logic in `to_payload()` has one critical bug (`pd.NaT` leaking through as a non-JSON-serializable value, crashing the entire /execute endpoint) and one medium bug (duplicate column names silently overwrite describe stats). The TypeScript type for describe values is too restrictive (missing `string`), and the DataPanel uses duplicate React keys when column names collide. The pin-to-canvas and snapshot rendering code is clean.

## Findings

### CRITICAL — `pd.NaT` in describe stats crashes JSON serialization of the entire `/execute` response
- **Location:** `emergentflow/server/payload.py:131–151`
- **Class:** Non-JSON-serializable value leaks through type guards
- **Confidence:** Confirmed
- **Description:** The describe-stats loop converts `describe(include="all")` cells into JSON-safe values using four type checks: `isinstance(val, float)` (NaN→None), `isinstance(val, (np.integer, np.floating))` (numpy→native), `isinstance(val, np.generic)` (other numpy→native), `isinstance(val, (pd.Timestamp, pd.Timedelta))` (ISO strings). `pd.NaT` — which appears as `mean`, `min`, `max`, `25%`, `50%`, `75%` when a datetime/timedelta column has zero valid values — is **not** caught by any of these checks: it is not `float`, not `np.generic`, and not `Timestamp`/`Timedelta`. It falls through into `col_stats`, passes through `_sanitize_nonfinite` unchanged, and then `json.dumps()` raises `TypeError: Object of type NaTType is not JSON serializable`. Since `_results_to_payloads` wraps `to_payload` without a try/except (`service.py:756–768`), this crash propagates as a 500 error for the entire `/execute` endpoint, wiping every node's results.
- **Evidence / Reproduction:** Run the following test (it fails on the current code):
  ```python
  import pandas as pd
  df = pd.DataFrame({
      "dt": pd.array([pd.NaT, pd.NaT], dtype="datetime64[ns]"),
      "val": [1.0, 2.0],
  })
  from emergentflow.server.payload import to_payload
  import json
  json.dumps(to_payload(df))  # raises TypeError
  ```
  Observed: `TypeError: Object of type NaTType is not JSON serializable`.
- **Impact:** Any DataFrame with an all-null datetime or timedelta column causes a 500 error on `/execute`, losing all node results. Realistic trigger: an upstream transform that produces an empty datetime column.
- **Remediation:** Add a catch-all `pd.isna(val)` guard after the existing type checks in the inner loop:
  ```python
  elif pd.isna(val):
      val = None
  ```
  This catches `pd.NaT` (and any other pandas NA type) without disturbing the pre-existing float-NaN→None conversion which runs first and is more specific.

### MEDIUM — Wrong TypeScript type for describe values (missing `string`)
- **Location:** `ui/src/store/execution.ts:13`
- **Class:** Type/contract mismatch
- **Confidence:** Confirmed
- **Description:** The `describe` field is typed as `Record<string, Record<string, number | null>>`, but `describe(include="all")` produces string values for categorical columns (`top`) and datetime/timedelta columns (`mean`, `min`, `max`, percentiles, and for timedelta, `std`). The golden snapshot confirms `cohort.top` is the string `"A"`, and the existing test `test_dataframe_datetime_timedelta_describe_is_json_safe` asserts `desc["ts"]["mean"]` is a string. At runtime these string values are handled gracefully by `DataPanel.tsx:163` (falls through to `String(val)`), but any future consumer that assumes all values are numbers would have a latent bug.
- **Evidence / Reproduction:** The golden snapshot at `tests/__snapshots__/test_regression_solo_path_goldens.ambr` shows `'top': 'A'` for the `cohort` column. The test `test_dataframe_datetime_timedelta_describe_is_json_safe` asserts `isinstance(desc["ts"]["mean"], str)`.
- **Impact:** Latent bugs in TypeScript consumers that treat describe values as `number`. The DataPanel itself works because it has a `typeof val === "number"` guard, but any UI component that directly accesses `describe[col][stat]` and expects a number would be wrong.
- **Remediation:** Change the value type in `ui/src/store/execution.ts:13` to include `string`:
  ```typescript
  describe?: Record<string, Record<string, number | string | null>>;
  ```

### LOW — Duplicate column names produce duplicate React keys in `DataPanel`
- **Location:** `ui/src/inspector/DataPanel.tsx:98,113,129`
- **Class:** React reconciliation issue (duplicate keys)
- **Confidence:** Confirmed
- **Description:** When a DataFrame has duplicate column names (e.g., `columns=["a", "a"]`), the `columns.map()` iterations at lines 98, 113, and 129 use `key={col}` as the React key. Duplicate keys cause React reconciliation warnings (and in edge cases, incorrect DOM diffing). The server-side `to_payload` already allows duplicate columns (`test_duplicate_column_dataframe_does_not_crash`), so this is a reachable code path.
- **Evidence / Reproduction:** A DataFrame with duplicate columns reaches `DataPanel`. The `columns` array `["a", "a"]` produces `<span key="a">` repeated, triggering the React warning "Encountered two children with the same key".
- **Impact:** Console warnings and potentially suboptimal React reconciliation. No data loss.
- **Remediation:** Use the column index as part of the key: `key={`${i}-${col}`}` on lines 98, 113, and 129. Also fix the sorting (`handleSort` uses the column name string which is ambiguous with duplicates; this is a pre-existing limitation but the key fix at least stops the React warning).

### MEDIUM — Duplicate column names in describe_stats silently overwrite
- **Location:** `emergentflow/server/payload.py:150`
- **Class:** State/consistency — silent data loss
- **Confidence:** Confirmed
- **Description:** When `desc.columns` has duplicate values (same column name string appearing in multiple positions), the assignment `describe_stats[str(col)] = col_stats` at line 150 overwrites the first column's describe stats with the second's. Only the last duplicate's stats survive. This is inconsistent with `payload["columns"]` which correctly reports `["a", "a"]` (both positions preserved).
- **Evidence / Reproduction:** Run:
  ```python
  import pandas as pd
  from emergentflow.server.payload import to_payload
  df = pd.DataFrame([[1, 2], [3, 4]], columns=["a", "a"])
  payload = to_payload(df)
  assert len(payload["describe"]) == 2  # fails: only 1
  ```
- **Impact:** Lost data — the second duplicate column's statistics are silently discarded. The `columns` array still says there are two columns, but describe only has one entry.
- **Remediation:** Use positional indexing keys when column names collide. In the outer loop, track seen column names and append a disambiguation suffix:
  ```python
  for col_idx, col in enumerate(desc.columns):
      col_name = str(col)
      if col_name in describe_stats:
          n = 2
          while f"{col_name}_{n}" in describe_stats:
              n += 1
          col_name = f"{col_name}_{n}"
      ...
      describe_stats[col_name] = col_stats
  ```

## Notes & unverified leads
- **`toReactFlow.ts:234` — `paramValue` uses `Array.find` which returns `undefined` for missing params.** This is handled correctly by the `typeof checks` at lines 252–260, which default to empty strings. Not a bug.
- **`Inspector.tsx:190` — Snapshot vertical offset uses total node count.** `offsetY = sourceNode.position.y + Object.keys(nodes).length * 30` means snapshot placement depends on total graph size, not source position or snapshot count. Layout choice, not a bug.
- **`payload.py:151` — Redundant `_sanitize_nonfinite` call on describe_stats.** The inner loop already converts `float NaN` to `None`. The outer call is harmless belt-and-suspenders. Not a bug.

## Coverage & limitations
- Reviewed all 10 files in the PR diff. The UI test suite (918 tests) was not re-run.
- Did not test the golden snapshot test or the regression path — only unit-level verification of the describe stats logic.
- Did not audit the `SnapshotNode.tsx` rendering beyond the data flow (payload → JSON.parse → props).
- Did not test the SSE streaming path (`/execute/stream`) which has separate serialization logic.