# Bug Hunt Report: emergent-flow (independent full-codebase sweep #4)

## Summary
- Scope reviewed: independent pass over the whole repo on top of the three earlier
  same-day reports. Weighted toward under-covered surfaces: `emergentflow/ir/`
  (`params`, `serialize`), `emergentflow/codegen/` (`compiler`, `executor`, `params`,
  `naming`), `emergentflow/ml/` (fit adapter, ensembles `blend/stack/calibrate/finalize`,
  `tune_model`, `optimize_threshold`, `apply_estimator`, `fit_and_label`,
  `fit_and_detect`, `evaluate`), `emergentflow/research/quality.py`,
  `emergentflow/eval/label.py`, `emergentflow/eval/run.py`,
  `emergentflow/recommend/` (metrics, collaborative helpers), `emergentflow/llm/templating.py`,
  `emergentflow/clean/`, and `ui/src/` (`IRToolbar`, `exportDataset`). Also re-verified the
  three fixes from reports #1-#3 (data contract `allow_extra_columns`, warehouse `dry_run`
  row estimate, executor MANY composite boundary) — all sound.
- Confirmed findings: 1 Medium (`ef.ml.evaluate` emits `roc_auc: nan` on a single-class
  eval set), 1 Low (`check_data_quality` `regex_match` flags `None`/NaN as a malformed value).
- Overall assessment: The codebase is mature and defensively written — 3748 tests pass with
  clean ruff/mypy, and the recently-fixed defects are correctly closed. The two genuine issues
  above are model-fit / data-quality edge cases: a silent `nan` metric that violates the
  function's own documented skip contract, and a blank-vs-malformed conflation in the quality
  regex gate. Neither is a crash on a common path; both are reachable and demonstrable.

## Findings

### Medium — `ef.ml.evaluate` reports `roc_auc: nan` instead of skipping it on a single-class eval set

- **Location:** `emergentflow/ml/__init__.py:238-241` (guard), docstring contract at `:197-198`
- **Class:** Silent wrong value / contract violation
- **Confidence:** Confirmed
- **Description:** The docstring promises roc_auc is "(skipped when `df` contains only one of
  the two classes)." The implementation guards the `roc_auc_score` call with
  `contextlib.suppress(ValueError)`, which was written for the pre-1.4 scikit-learn contract
  where a single-class `y_true` raised `ValueError`. Since scikit-learn 1.4 (project runs 1.9.0),
  `roc_auc_score` returns `nan` instead of raising, so the exception is never raised, the
  suppress never fires, and `metrics["roc_auc"] = nan` is written unconditionally.
- **Evidence / Reproduction** (sklearn 1.9.0, verified):
  ```python
  import pandas as pd, warnings
  from emergentflow.ml import fit_estimator, evaluate
  train = pd.DataFrame({"a":[0.1,0.2,0.3,0.9,0.95,1.0], "y":[0,0,0,1,1,1]})
  model = fit_estimator(train, estimator="LogisticRegression", target="y")
  one_class = pd.DataFrame({"a":[0.1,0.2,0.15], "y":[0,0,0]})
  r = evaluate(model, one_class)
  # -> r.metrics == {'accuracy':1.0,'precision':0.0,'recall':0.0,'f1':0.0,'roc_auc': nan}
  #    'roc_auc' in r.metrics == True
  # UnexpectedMetricWarning: Only one class is present in y_true...
  ```
  Raw `roc_auc_score([0,0,0],[.1,.2,.3])` returns `nan` (does not raise), confirming the guard
  can no longer trigger. The node `ul.ml.evaluate` (`emergentflow/nodes/examples/evaluate.py`)
  returns this `EvaluationResult` straight to the canvas inspector, so the `nan` is user-facing.
- **Impact:** A `nan` metric is silently present wherever the documented contract says it will be
  absent. Any downstream consumer that aggregates over the metric dict (`sum`, `max`, `mean`,
  "best model" comparison, JSON persistence) receives `nan` and propagates it, instead of the
  metric being cleanly omitted.
- **Remediation:** Guard on the value, not on the legacy exception type — only emit roc_auc when
  it is finite:
  ```python
  if hasattr(model.estimator, "predict_proba"):
      proba = model.estimator.predict_proba(df[model.feature_names])
      if len(y_true.unique()) > 1:
          metrics["roc_auc"] = float(roc_auc_score(y_true, proba[:, 1]))
  ```
  (A NaN can also arise from constant probabilities; the finite check is the robust option.)
  Re-run the repro above and assert `'roc_auc' not in r.metrics`.

### Low — `check_data_quality` `regex_match` flags `None`/NaN as a malformed value

- **Location:** `emergentflow/research/quality.py:94-104` (specifically `:97`)
- **Class:** Missing-value mishandling / false positive
- **Confidence:** Confirmed
- **Description:** `_check_regex_match` coerces every cell via `.astype(str)` before applying the
  pattern. Pandas renders a `None`/`NaN` as the literal string `"nan"`, so a missing cell is
  flagged as not matching the pattern. A blank (missing) cell is distinct from a malformed
  (non-matching) string, and the module already offers `non_null` as the deliberate expectation
  for enforcing presence — but with `regex_match` there is no way to allow blanks while still
  validating the non-blank values, so a column with legitimate missing values fails wholesale.
- **Evidence / Reproduction** (verified):
  ```python
  import pandas as pd
  from emergentflow.research.quality import check_data_quality
  from emergentflow.research.errors import DataQualityError
  df = pd.DataFrame({"email": ["a@x.com", "b@y.com", None, "c@z.com"]})
  exp = [{"type": "regex_match", "column": "email", "pattern": r".+@.+\..+"}]
  check_data_quality(df, exp)
  # -> DataQualityError: ... 1 violation(s) found
  #    {'expectation':'regex_match','column':'email','detail':"1 value(s) not matching ..."}
  ```
  The offending value is the `None`, not a malformed email.
- **Impact:** False failures on the data-quality/`assert_data` gate for any column that legitimately
  contains blanks, requiring callers to split expectations or drop rows first. Misleading detail
  ("1 value(s) not matching") for a blank cell.
- **Remediation:** Compare against the non-null subset before stringifying, so `None`/NaN are
  treated as out-of-scope for a string regex rather than as non-matching strings:
  ```python
  column = exp["column"]
  pattern = exp["pattern"]
  non_null = frame[column].dropna()
  bad = int((~non_null.astype(str).str.match(pattern)).sum())
  ```
  (Keeps the existing "value(s) not matching" semantics for real strings; nulls are a separate
  concern owned by the `non_null` expectation. Note this drops rows with nulls from the regex
  count entirely as opposed to counting them — if the intent is to ALSO reject nulls, the caller
  should add a `non_null` expectation.)

## Notes & unverified leads

- **`ef.ml.evaluate` binary `proba[:, 1]` when `predict_proba` returns fewer than 2 columns.**
  The `n_classes == 2` guard (from `classes_` or `len(set(y_true))`) normally guarantees two
  columns, but if `classes_` is present with 2 entries yet the fitted estimator produces a single
  probability column (unusual), `proba[:, 1]` would `IndexError`. Could not be triggered with the
  curated estimators; left unverified.
- **`check_data_quality` `allow_extra_columns` fix** re-verified — the fixed `extra =
  present_columns - (expected_columns | dtype_columns)` behaves correctly for the reported case;
  no incomplete-fix regression found.
- **`VotingClassifier(voting="soft")` in `blend_models`** fails if a base classifier lacks
  `predict_proba` — deliberately not validated up front, but a runtime sklearn `AttributeError` is
  surfaced rather than a typed error. Not a correctness bug; noted as a UX fragility.

## Coverage & limitations
- Exercised the SQLite-backed IR + codegen + executor + ml + research + eval + recommend +
  llm + clean surfaces via the full test suite (3748 passed, 103 skipped) and targeted repro
  scripts for the two findings.
- The live cloud-driver warehouse paths (Postgres/Redshift/BigQuery) and the React canvas were
  reviewed statically only; the recently-fixed UI stale-state bugs (reports #1-#3) were confirmed
  closed in `IRToolbar.tsx`.
- No concurrency stress harness was run against `SessionStore`/`chat_runner`; covered by unit
  tests only.
- This was the fourth full-coverage pass on the same branch; findings above are the verifiable
  deltas our prior passes and the existing suite did not already catch.