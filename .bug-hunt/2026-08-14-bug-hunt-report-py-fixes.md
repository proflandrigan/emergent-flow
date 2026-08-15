# Bug Hunt Report: emergentflow (Python package)

- **Date:** 2026-08-14
- **Branch:** `feat/agent-onboarding-and-oom`
- **Team:** Bug-Hunt skill (Discovery → Verify → Report loop)

## Summary
- Scope reviewed: `emergentflow/eval/` (score, judge, export), `emergentflow/validity/rules/skew.py`,
  `emergentflow/timeseries/`, `emergentflow/cli.py` + `emergentflow/server/service.py` run-record
  hashing, `emergentflow/research/` (quality, lineage, report). UI excluded.
- Confirmed findings: 1 Medium, 2 High-adjacent fixes verified as deterministic, 1 Low. All four
  confirmed, fixed, and regression-tested.
- Overall assessment: The package is clean (3814 passing pre-hunt, mypy/ruff clean). The confirmed
  defects are narrow but real: a JSON-Schema scorer that rejects valid integer-valued floats and
  numpy scalars (wrong scores), a train/serve-skew rule that over-reports a single count-mismatch
  as multiple findings, a run-record `graph_hash` that ignores graph-level param overrides (so the
  canvas reports two behaviourally-different runs as "identical graphs"), and a
  `seasonal_decompose` period bound that leaked a raw statsmodels `ValueError` past the typed-error
  boundary. Reproductions for each are below; every one is now covered by a regression test.

## Findings

### [HIGH] — Train/serve-skew rule over-reports a single count-mismatch as N findings
- **Location:** `emergentflow/validity/rules/skew.py:226-234`
- **Class:** Logic error / off-by-one in count diff
- **Confidence:** Confirmed
- **Description:** When a transform type is applied more times on one path than the other, the rule
  emitted ONE finding per node of the over-represented type rather than per count *delta*. Train
  applying `transform.scale_features` twice and serve once is a discrepancy of exactly one extra
  application, but **both** train scale nodes were reported as "applied on training but NOT on
  scoring", double-counting the finding.
- **Evidence / Reproduction:** Built the graph from `test_train_serve_skew_reports_count_mismatch_not_order`
  (src → sa→sb→fit; src→sc→pred; lm→pred). Before the fix `run_validity_checks` returned **2**
  `train_serve_skew` findings (node `sa` and node `sb` both "missing"); the count delta is 1.
  After the fix exactly **1** finding is returned.
- **Impact:** Misleading validity output — analysts see duplicate warnings for a single real skew,
  inflating the effective severity and undermining trust in the rule's finding count.
- **Remediation:** Compute the count delta per type and emit a capped number of findings
  (`train_by_type[train_type][:delta]` / `predict_by_type[predict_type][:delta]` where
  `delta = t_count - predict_counts.get(type, 0)`), preserving node-id-deterministic selection.
  Regression: `test_train_serve_skew_emits_one_finding_per_count_delta` asserts `len(skew) == 1`.

### [HIGH] — Run-record `graph_hash` ignores graph-level param overrides
- **Location:** `emergentflow/server/service.py:841` and `emergentflow/cli.py:277`
- **Class:** State consistency / wrong hash input
- **Confidence:** Confirmed
- **Description:** Both the server's `_save_run_record` and the CLI `run` command hashed only the raw
  graph payload, omitting resolved graph-level param overrides. The canvas diffs `graph_hash`
  (`ui/src/execution/RunsPanel.tsx:219`) to decide "Identical graphs" vs "Different graphs", so two
  runs of the same graph with different `?params`/`--param` values were reported as identical.
- **Evidence / Reproduction:** Called `_save_run_record` twice with the same `Graph` (graph-level
  param `epochs`) but `params={"epochs": 10}` vs `params={"epochs": 20}`; both produced the **same**
  `graph_hash` before the fix, different after. Deterministic for identical params (same override →
  same hash).
- **Impact:** The run store and the canvas compare UI misclassify behaviorally-different runs as the
  same graph, wrong for reproducibility reviews and run-to-run diffing.
- **Remediation:** Fold the resolved params in: `resolved = resolve_graph_params(graph, overrides=params)
  if params else None; hash_source = {**payload, "resolved_params": resolved}`. Applied in both
  `service.py` and `cli.py`. Regression: `test_graph_hash_includes_param_overrides`.

### [MEDIUM] — JSON-Schema scorer falsely rejects integral floats and numpy scalars
- **Location:** `emergentflow/eval/score.py:74-87` (now `_is_integer`)
- **Class:** Type coercion / boundary
- **Confidence:** Confirmed
- **Description:** `{"type": "integer"}` matched against `json.loads("3.0")` (the float `3.0`) scored
  0.0 because `isinstance(3.0, int)` is False — yet JSON-Schema defines `integer` as a number with
  zero fractional part, so `3.0` is a valid integer. `numpy.int64/numpy.float64` scalars (common from
  pandas rows) also failed both `integer` and `number` because they are not `isinstance` subclasses of
  the Python builtins.
- **Evidence / Reproduction:**
  ```python
  _score_json_schema('3.0', {'schema': {'type':'integer'}}, None)  # was 0.0, now 1.0
  _score_json_schema('3.5', {'schema': {'type':'integer'}}, None)  # 0.0 (correct)
  _score_json_schema(np.int64(3), {'schema': {'type':'integer'}}, None)  # was 0.0, now 1.0
  ```
- **Impact:** A deterministic "must be an integer" eval scorer silently scored valid integer output
  as a failure, under-reporting variant quality.
- **Remediation:** Add a `_is_integer` helper using `numbers.Integral` and `float(data).is_integer()`
  for integral floats / numpy reals, and accept `isinstance(data, numbers.Real)` for `number`.
  `bool` remains rejected for numeric types. Regression: `test_score_json_schema_accepts_integral_float_and_numpy_scalar`.

### [LOW] — `seasonal_decompose` leaks a raw statsmodels `ValueError` for an oversized period
- **Location:** `emergentflow/timeseries/__init__.py:265-271`
- **Class:** Boundary / typed-error contract
- **Confidence:** Confirmed
- **Description:** Only `period >= 1` was validated. A period too large for the series
  (`len(series) < 2*period`) was passed straight to statsmodels, which raised a bare
  `ValueError: x must have 2 complete cycles requires N observations`, breaking the family's
  "typed `TimeseriesError` at the boundary" contract.
- **Evidence / Reproduction:** `seasonal_decompose(df10, target="a", period=9)` raised
  `ValueError` (10 rows, period 9). After the fix it raises `TimeseriesError` with the message
  "period must allow at least 2 complete cycles".
- **Impact:** Opaque library error instead of the documented typed error; users can't catch the
  timeseries failure type.
- **Remediation:** After building the series, guard `if len(series) < 2 * period: raise
  TimeseriesError(...)`. Regression: `test_seasonal_decompose_period_too_large_raises_typed_error`.

## Notes & unverified leads
- `emergentflow/eval/export.py:88` `float(score)` crashes on a non-numeric string score — judged
  caller misuse (score is numeric by contract; `ef.eval.label` only ever emits floats/None), so not
  promoted to a finding.
- `emergentflow/cli.py:155` float-typed `--param` coerced to an `int` keeps its `int` value — benign
  in Python (an int behaves as a float downstream); dropped.
- `emergentflow/research/quality.py` range-check treats NaN as in-range while `regex_match`/
  `allowed_values` flag it — a defensible design difference rather than a defect; left as-is.
- An `httpx.AsyncClient` crossing a closed event loop in the `emergentflow mcp` CLI path was
  suspected but **refuted** empirically: httpx handles the pool across loops (repro returned HTTP 200).
- `validity/rules/metrics.py`, `temporal.py`, `eval/judge.py`, `eval/label.py`, and
  `research/lineage.py` were swept; the suspected issues there were edge-semantics or would need
  single-user/malformed inputs to manifest and did not meet the confirmation bar.

## Coverage & limitations
- Read-focused on `eval/`, `validity/rules/`, `timeseries/`, `research/`, `cli.py`, and
  `server/service.py`. The `ui/` canvas was out of scope, and deep auditing of `ml/`, `data/warehouse/`,
  `collab/`, and `recommend/` was skipped (heavily covered by the immediately-preceding 2026-08-14 hunts).
- Every confirmed finding was reproduced with concrete input in the repo venv and pinned by a
  regression test; full suite (3818 passed), `ruff`, `mypy`, and the ADR-0002 equivalence gate are green.
