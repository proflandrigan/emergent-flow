# Bug Hunt Report: emergent-flow Python package (focused sweep on least-covered surfaces)

## Summary
- Scope reviewed: a fresh targeted pass over `emergentflow/ml/` (post-fit ops: `optimize_threshold`),
  `emergentflow/data/warehouse/` (`spec_compiler`), and `emergentflow/connections/profiles.py`,
  weighted toward correctness bugs that silently produce wrong SQL or wrong persisted state, plus the
  ml-branch focus area. Discovery used codegraph and parallel sub-agent sweeps across the broader
  package (clean, validity, embed, data/warehouse, data/http, nodes); every reported lead was
  verified with a minimal runtime reproduction. The full suite is green before and after (3769 passed,
  103 skipped; ruff, format, and mypy all clean).
- Confirmed findings: 1 Medium, 2 Low (all three fixed + regression-tested).
- Overall assessment: The package remains defensively written. The one genuinely impactful correctness
  defect found is that a `query-builder` `IN` predicate with an empty member list compiles to `IN ()`,
  which is invalid SQL in every dialect and crashes at the database with an opaque parser error. The
  other two are lower-severity input-handling gaps (a persisted-profile `name` field silently
  overriding the TOML table key, and `optimize_threshold` rejecting a numeric class label passed as the
  raw value). Numerous leads from the sub-agent sweeps were examined and refuted (e.g. `semi_join`
  row alignment is safe because it is a `how="left"` merge that preserves left order; `_coerce_labels`
  non-float NaNs are caught by the downstream mixed-type guard).

## Findings

### Medium — Empty `IN` membership list compiles to invalid SQL (`col IN ()`)
- **Location:** `emergentflow/data/warehouse/spec_compiler.py:126-135`
- **Class:** Boundary / invalid output -> crash on reachable input
- **Confidence:** Confirmed
- **Description:** `_build_predicate` builds an `exp.In` node from `value` without checking whether the
  list is empty. An empty list renders `col IN ()`, which is a syntax error in PostgreSQL, DuckDB,
  BigQuery, and every other SQL dialect. The query-builder node/API does not guard against an empty
  membership set upstream, so any categorical `IN` filter whose selected values collapse to `{}`
  reaches the database as malformed SQL.
- **Evidence / Reproduction:** `compile_spec({"source":"sales","where":[{"column":"region","op":"IN","value":[]}]}, "duckdb")`
  returns `'SELECT * FROM sales WHERE region IN ()'`. Sent to DuckDB:
  ```python
  con.execute("SELECT * FROM sales WHERE region IN ()")
  # -> duckdb.ParserException: Parser Error: syntax error at or near ")"
  ```
- **Impact:** A reachable query-builder input produces a confusing database parser error instead of a
  clear validation error or a gracefully-empty result; for a scripted pipeline this aborts the run.
- **Remediation:** Reject the empty membership set in `_build_predicate`:
  ```python
  if not isinstance(value, list):
      raise SpecValidationError(
          f"IN predicate requires a list value, got {type(value).__name__}")
  if not value:
      raise SpecValidationError(
          "IN predicate requires a non-empty list of values; its membership set "
          "cannot be empty (an empty set would compile to invalid SQL like `x IN ()`).")
  ```
  Regression test: `tests/test_warehouse_spec_compiler.py::test_empty_in_predicate_raises`.

### Low — Profile `name` field in a TOML body silently overrides the table key
- **Location:** `emergentflow/connections/profiles.py:265`
- **Class:** State & consistency / silent wrong key
- **Confidence:** Confirmed
- **Description:** `load_profiles` builds each payload as `{"name": name, **body}` where `name` is the
  TOML table key. If a table body also contains a `name` key (`{**[body]}`, it overrides the injected
  key), so the profile is stored under the body's `name` via `ProfileStore.add` (keyed on
  `profile.name`). Lookups by the table key then fail with `UnknownConnectionError` even though the
  table clearly exists.
- **Evidence / Reproduction:**
  ```toml
  [aliased]
  kind = "warehouse"
  engine = "postgres"
  dialect = "duckdb"
  host = "h"
  database = "db"
  name = "sneaky"
  ```
  `load_profiles(path)` stores a profile named `"sneaky"`; `store.get("aliased")` raises
  `UnknownConnectionError` and only `"sneaky"` is reachable.
- **Impact:** A profile whose table key is referenced by graphs/scripts becomes silently shadowed by an
  unrelated `name` in the body, causing confusing "no connection profile named" failures.
- **Remediation:** Let the table key always win: `payload = {**body, "name": name}`.
  Regression test: `tests/test_connections_profiles.py::test_load_profiles_table_key_wins_over_body_name`.

### Low — `optimize_threshold` rejects a numeric class label passed as the raw value
- **Location:** `emergentflow/ml/__init__.py:532`
- **Class:** Type & coercion / rejects valid input with confusing error
- **Confidence:** Confirmed
- **Description:** `positive_class` is validated by comparing `pos not in {str(c) for c in classes}`,
  but `pos` is used verbatim when provided. For a classifier with numeric labels (e.g. `{0, 1}`), a
  user naturally passing `positive_class=1` (the actual label) is told
  `unknown positive_class 1; expected one of ['0', '1']`. The default path already stringifies
  (`str(classes[1])`), so only an explicitly-passed raw numeric label is rejected.
- **Evidence / Reproduction:** A binary `LogisticRegression` fit on labels `{0, 1}`:
  ```python
  optimize_threshold(model, df, target="y", positive_class=1)
  # -> ValueError: unknown positive_class 1; expected one of ['0', '1']
  ```
  after fix, returns `positive_class == "1"` (string, consistent with the `str | None` annotation and
  the existing `positive_class="low"` test).
- **Impact:** Low — the branch's own post-fit feature rejects a natural input with a confusing error;
  no silent wrong result.
- **Remediation:** Normalize the provided value once: `pos = str(positive_class) if positive_class is not None else str(classes[1])`.
  Regression test: `tests/test_ml_postfit.py::test_optimize_threshold_accepts_numeric_positive_class`.

## Notes & unverified leads (optional)
- `data/http/fetch.py` offset/`page` pagination never sends `page_size` as a request parameter — only
  `offset_param`/`page_param` are emitted, so the client cannot control how many records each page
  returns and results depend on an implicit server default. This can silently overlap or gap pages on
  an API whose default page size differs. Looked real when read, but unresolved without a concrete
  API contract for the param name (`limit` vs `size` vs `page_size`), so it was recorded but not fixed.
- `spec_compiler._build_join` and the `order_by` dict path raise raw `KeyError`/`TypeError` on
  malformed specs (join `on` not a list; `order_by` dict missing `"column"`). These are missing
  validation on malformed input rather than wrong behavior on valid input; the `BETWEEN`/`IN`
  validation exists, so those two paths are inconsistently unvalidated but not correctness bugs on
  well-formed specs.
- The clean/validity/embed and remaining data/warehouse sub-agent sweeps produced many additional
  leads; almost all were refuted on inspection (e.g. `semi_join` mask alignment is order-safe because
  a `how="left"` merge preserves the left frame's row order). Those that require a concrete API or a
  crafted malformed-spec input to manifest are listed above rather than promoted to findings.

## Coverage & limitations
- Focused on the ml post-fit area, `data/warehouse/spec_compiler`, and `connections/profiles`, with
  sub-agent sweeps across `clean`, `validity`, `embed`, `data/http`, `data/warehouse` adapters, and
  `nodes/contract`. Not exhaustively re-reviewed the surfaces already hunted repeatedly same-day
  (recommender, stats, timeseries, collab, research/lineage, explain, Full-codebase #4/#5).
- The full test suite (3769 passed / 103 skipped), ruff, `ruff format --check`, and mypy were all
  green before and after the fixes.