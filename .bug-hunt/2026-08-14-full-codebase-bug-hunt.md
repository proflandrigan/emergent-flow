# Bug Hunt Report: Emergent Flow (full codebase scan)

- **Date:** 2026-08-14
- **Branch:** `feat/agent-onboarding-and-oom` @ `0aa0b71`

## Summary

- Scope reviewed: `emergentflow/stats/`, `emergentflow/clean/`, `emergentflow/recommend/`,
  `emergentflow/collab/`, `emergentflow/server/`, `emergentflow/codegen/`,
  `emergentflow/clients.py`, `emergentflow/llm/`, `emergentflow/script/`, `emergentflow/ml/`,
  `emergentflow/data/` (incl. warehouse), `emergentflow/connections/`, `emergentflow/embed/` and
  the `ui/` React canvas. Parallel hunts were run per-subsystem; every finding below was
  reproduced with concrete input in the repo venv / vitest.
- Confirmed findings: 1 High, 5 Medium, 4 Low.
- Overall assessment: The codebase is heavily hunted already (32 prior reports), and the vast
  majority of high-risk paths are guarded. The one High is a real contract violation in
  recommend `temporal_split` that empties the train half for single-interaction (sparse) data.
  The remaining findings are mostly edge-case robustness gaps (untyped crashes, misleading
  metrics/docstring divergence, one UI race and one store-out-of-band event drop). None are
  data-corruption-level, but several produce crashes or incorrect values on realistic inputs.

## Findings

### [HIGH] — `temporal_split` routes single-interaction users to TEST, leaving the training half empty
- **Location:** `emergentflow/recommend/__init__.py:901-904`
- **Class:** Boundary / off-by-one (`iloc[-0:]` == `iloc[0:]`)
- **Confidence:** Confirmed
- **Description:** For a user with exactly one interaction, `n_test = 0`
  (`max(1, ...)` only applies `n >= 2`). Then `ordered.iloc[-n_test:]` evaluates as
  `ordered.iloc[0:]` (the **whole** row → test) and `ordered.iloc[:-0]` as `ordered.iloc[:0]`
  (empty → train). The inline comment explicitly states the opposite intent: "A single-interaction
  user (no half to split) keeps their row in train."
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({"user":[0,1,2], "item":["x","y","z"], "rating":[5.,4.,3.], "ts":[1,2,3]})
  train, test = temporal_split(df, user_col="user", item_col="item", value_col="rating",
                               timestamp_col="ts", test_ratio=0.5)
  # observed: train n_interactions=0 n_users=0 | test n_interactions=3 n_users=3
  ```
  With all/sparse users having one interaction the fitted half is completely empty.
- **Impact:** For sparse interaction data (the common real-world case), evaluation splits
  produced by `temporal_split` can yield an empty training set, breaking the recommend
  training/eval pipeline and producing nonsensical metrics.
- **Remediation:** When `n < 2`, keep the whole row in train and nothing in test:
  ```python
  n = len(ordered)
  if n >= 2:
      n_test = max(1, min(n - 1, round(n * test_ratio)))
      test_parts.append(ordered.iloc[-n_test:])
      train_parts.append(ordered.iloc[:-n_test])
  else:
      train_parts.append(ordered)
  ```

### [MEDIUM] — `evaluate` stores `roc_auc: nan` for a single-class eval frame instead of skipping it
- **Location:** `emergentflow/ml/__init__.py:238-241`
- **Class:** Logic error / docstring divergence (guard checks model classes, not eval frame)
- **Confidence:** Confirmed
- **Description:** The docstring (line 197) promises roc_auc is "skipped when `df` contains only
  one of the two classes." The guard instead checks `n_classes == 2` derived from the **model's**
  `classes_`, so on an eval frame containing only one class it still calls `roc_auc_score`,
  which yields `nan` (emit `UndefinedMetricWarning`, not `ValueError`, so
  `contextlib.suppress(ValueError)` misses it).
- **Evidence / Reproduction:** Fitted a `RandomForestClassifier` on `target ∈ {0,1}`, then
  `evaluate(model, df[df.target == 0])` → `{'accuracy': 1.0, 'precision': 0.0, 'recall': 0.0,
  'f1': 0.0, 'roc_auc': nan}`.
- **Impact:** Misleading NaN metric surfaced to users/canvas rather than the documented omission;
  un-plottable and signals an error that didn't happen.
- **Remediation:** Gate roc_auc on the eval frame actually containing both classes:
  ```python
  if hasattr(model.estimator, "predict_proba"):
      proba = model.estimator.predict_proba(df[model.feature_names])
      if y_true.nunique() >= 2:
          try:
              metrics["roc_auc"] = float(roc_auc_score(y_true, proba[:, 1]))
          except ValueError:
              pass
  ```

### [MEDIUM] — `correlation` crashes on explicit non-numeric `columns`
- **Location:** `emergentflow/stats/__init__.py:954`
- **Class:** Unhandled type / contract inconsistency
- **Confidence:** Confirmed
- **Description:** With `columns` given, `target = df[columns]` is passed straight to `.corr()`
  without the `select_dtypes(include="number")` filter that the default path applies, so a
  string column in the explicit list raises `ValueError: could not convert string to float`.
  Reachable through the `stats.correlation` node.
- **Evidence / Reproduction:**
  ```python
  correlation(pd.DataFrame({"a":[1.,2.,3.], "name":["x","y","z"]}), columns=["a", "name"])
  # ValueError: could not convert string to float: 'x'
  ```
- **Impact:** Crashes a documented op on a valid (shady but possible) input; inconsistent with
  the default path which silently filters numeric columns.
- **Remediation:** Filter the explicit selection to numeric columns (consistent with the default
  path) or reject non-numeric columns with a clear error:
  ```python
  target = df[columns].select_dtypes(include="number")
  if target.shape[1] < len(columns):
      raise ValueError(...)  # or silently drop, matching the None path
  ```

### [MEDIUM] — `test` connection route falsely reports an existing LLM profile as missing
- **Location:** `emergentflow/server/service.py:1401-1409` (via `emergentflow/data/warehouse/profiles.py:47-63`)
- **Class:** API contract inconsistency / misleading error
- **Confidence:** Confirmed
- **Description:** `test_connection_route` calls `store.get(name)` on a warehouse-only
  `ProfileStore` (from `data.warehouse.profiles.load_profiles`), which deliberately discards LLM
  profiles at read time. Testing a legitimately listed LLM profile therefore raises
  `UnknownConnectionError: No connection profile named 'my_llm'. Known profiles: my_pg.`
  even though `GET /connections` lists it.
- **Evidence / Reproduction:** Create `my_llm` (kind=llm) and `my_pg` profiles; `GET /connections`
  → 200 lists both; `POST /connections/my_llm/test` → `422 UnknownConnectionError: No connection
  profile named 'my_llm'`.
- **Impact:** Public endpoint contract ("probe one named connection profile") is broken for a
  listed profile; misleading "profile does not exist" for a profile that does.
- **Remediation:** Test-route should resolve the profile from the shared/unfiltered store that the
  listing uses (LLM and warehouse profiles have distinct test paths), or explicitly return a clear
  "LLM connections don't support test" 4xx instead of a false "not found".

### [MEDIUM] — `prepare_interactions` raises untyped `TypeError` on mixed-type user/item ids
- **Location:** `emergentflow/recommend/interactions.py:104-105`
- **Class:** Type coercion / missing typed error
- **Confidence:** Confirmed
- **Description:** `from_dataframe` does `sorted(df[user_col].unique().tolist())`, which raises a
  raw `TypeError: '<' not supported between instances of 'str' and 'int'` on mixed-type ids,
  leaking out of the public `prepare_interactions` seam as an untyped crash instead of an
  `InvalidRecommenderParamsError`.
- **Evidence / Reproduction:**
  ```python
  prepare_interactions(pd.DataFrame({"user":[1,"u2",3], "item":["i1","i2","i3"], "rating":[1.,2.,3.]}),
                       user_col="user", item_col="item", value_col="rating")
  # TypeError: '<' not supported between instances of 'str' and 'int'
  ```
- **Impact:** Untyped crash for a realistic spoilt-input case; inconsistent with the module's
  typed validation behavior elsewhere.
- **Remediation:** Before sorting, normalize each id column to a comparable type (e.g. cast to
  `str`) or coerce such that comparison is well-defined, and raise a typed error on mixed types.

### [MEDIUM] — Out-of-order run-detail fetches overwrite the user's latest selection (UI)
- **Location:** `ui/src/execution/runsStore.ts:40-63`
- **Class:** Race condition (no cancellation/ordering guard)
- **Confidence:** Confirmed
- **Description:** `selectRun`/`selectCompareRun` await `getRun(runId)` then unconditionally set
  state, so two rapid selections can resolve out of order and the stale earlier detail wins.
  `selectCompareRun` additionally never sets the loading flag.
- **Evidence / Reproduction:** Vitest with two deferred `getRun` mocks; `selectRun("A")` then
  `selectRun("B")`; resolve B first then A → `selectedRunId === "runA"` (expected `"runB"`).
- **Impact:** Selected run detail flickers to a stale run after a fast re-selection.
- **Remediation:** Guard with a monotonic token/cancel: ignore a response if a newer selection has
  superseded it, and set loading for `selectCompareRun`.

### [LOW] — ranking metrics can exceed 1.0 on duplicate recommended items
- **Location:** `emergentflow/recommend/metrics.py:41-53` (NDCG), `:68-78` (MAP)
- **Class:** Arithmetic / metric bound violation
- **Confidence:** Confirmed
- **Description:** DCG counts every occurrence of an item in `relevant` within `recommended[:k]`,
  while IDCG is built from distinct relevant items (`len(relevant)`), so a repeated relevant item
  pushes NDCG > 1. MAP similarly allows per-position precision sum to exceed
  `min(k, len(relevant))`.
- **Evidence / Reproduction:** `_ndcg_at_k([1,1], {1}, 10)` → `1.6309...`; `_average_precision_at_k([1,1],{1},10)` → `2.0`.
- **Impact:** Boundary violation in documented public ranking-metric helpers. Currently latent
  (bundled recommenders emit unique items) but any future recommender emitting a duplicate
  silently corrupts metric bounds.
- **Remediation:** Count only first occurrences of each relevant item when accumulating DCG /
  precision (e.g. track `seen` and skip already-scored relevant items).

### [LOW] — `co_missingness` crashes on duplicate column names in `columns`
- **Location:** `emergentflow/stats/eda.py:152`
- **Class:** Null/duplicate handling
- **Confidence:** Confirmed
- **Description:** `columns=['a','a']` yields duplicate labels in `target`, making `mask['a']` a
  DataFrame so `float((mask[i] & mask[j]).mean())` raises `TypeError: cannot convert the series`.
  Sibling `correlation` handles the same input.
- **Evidence / Reproduction:** `co_missingness(pd.DataFrame({"a":[1.,None,3.],"b":[None,2.,3.]}), columns=["a","a"])` → `TypeError: cannot convert the series to <class 'float'>`.
- **Impact:** Crashes an op on duplicated columns; inconsistent with `correlation`.
- **Remediation:** Dedupe `columns` (or validate uniqueness) before building the mask, e.g.
  `cols = list(dict.fromkeys(columns))`.

### [LOW] — SSE polling fallback drops `run_completed` (UI)
- **Location:** `ui/src/session/sessionClient.ts:409-444` (consumed by `sessionStore.ts:200-203`)
- **Class:** Missing event handling / stale UI
- **Confidence:** Confirmed
- **Description:** The EventSource-less poll loop only ever synthesizes `graph_replaced` /
  `chat_narration_added`; there is no path emitting `run_completed`, so an agent-completed run
  never triggers `fetchRuns()` when EventSource is unavailable.
- **Evidence / Reproduction:** With `EventSource` removed, a session poll returns
  `['graph_replaced']` but never `run_completed`.
- **Impact:** Runs panel not refreshed after an agent run in the polling fallback path.
- **Remediation:** Emit a synthesized `run_completed` (from the poll snapshot delta) in the poll
  loop, mirroring the EventSource path.

### [LOW] — stats scale-guard error message wording contradicts the behavior
- **Location:** `emergentflow/stats/scale.py:51`
- **Class:** Cosmetic / misleading message
- **Confidence:** Confirmed
- **Description:** Guard message ends "Refusing to protect the shared server from OOM" — the
  reverse of what the guard actually does (it refuses the operation **to** protect the server).
- **Impact:** Confusing error text when the guard fires.
- **Remediation:** Reword to "...Refusing the operation to protect the shared server from OOM."

## Notes & unverified leads

- **codegen/llm/script/api:** No reproducible defects; equivalence gate (331) plus a 3000-graph
  DAG fuzzer and a 20,000-trial naming fuzzer all passed. `is_inspectable` returns `True` for any
  dataclass without recursing into non-serializable fields — documented deliberate design, noted
  not a bug.
- **collab:** The `collab`/server hunt agent's output was muddled; its connections lead was
  independently reproduced by the ml/data hunt and is reported above. Remaining collab session
  logic showed no reproducible defect.
- **Deep recommenders (`ncf`, `two_tower`, `gru4rec`) and implicit (`als`, `bpr`):** could not be
  executed (torch/implicit not installed); their negative-sampling/footprint edges remain
  unverified.
- **Block-wise KNN, footprint guard boundary, `compare` metrics, MCP bridge reparse,
  `await_verdict`:** probed and refuted by earlier hunts — no bug.

## Coverage & limitations

- Deep/implicit recommender paths not executed (optional deps absent). Live end-to-end agent chat
  over real TCP FastMCP and the `npm run build` production bundle were not run. Postgres/BigQuery/
  Redshift live drivers not exercised (tested via fixtures/TestClient only).