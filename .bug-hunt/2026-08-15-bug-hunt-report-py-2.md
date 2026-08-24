# Bug Hunt Report: emergentflow (Python package)

- **Date:** 2026-08-15
- **Branch:** `feat/agent-onboarding-and-oom`
- **Team:** Bug-Hunt skill (Discovery → Verify → Report loop)

## Summary
- Scope reviewed: fresh sweep prioritizing modules not deep-dived in the immediately-preceding
  2026-08-13/14/15 hunts — `research/` (lineage, quality, reproducibility, report),
  `stats/` (anova/kruskal CI + summaries + eda), `ml/` (reduce_dimensions vs fit_transform
  naming), `eval/` (label, run, judge, score, export), `data/` (http, warehouse, documents),
  `llm/` (budget, pricing, templating, gateway), `clean/` verb families, `explain/`,
  `viz/`, `ir/` (mutation, params, serialize, migrate, graph), `codegen/params` + executor,
  `validity/`. Discovery used the codegraph index plus three parallel read-the-source explore
  agents to cast a wide net; every shortlist candidate was then verified by writing and running
  a minimal reproduction.
- Confirmed findings: **1 Medium, 2 Low.** All three reproduced end-to-end, fixed, and pinned by
  new regression tests. A further set of promising leads was refuted (proven not bugs) or left as
  unverified notes rather than promoted — most notably the stats noncentral-F CI endpoint swap,
  which a monotonicity check proved is actually correct.
- Overall assessment: The package remains in exceptionally good shape — the full suite
  (**3832 passed**, up 4 from the regression tests added here), ruff, and mypy are all green. The
  findings are genuine but narrow: one wrong-provenance metadata bug in column-lineage (reported
  `SOURCE` where the module's own contract requires `UNKNOWN`), one silently-NaN statistical-test
  result when a group is entirely missing its values, and an uncaught `CycleError` crash in two
  lineage entry points on a degenerate cyclic graph that the sibling function deliberately
  tolerates.

## Findings

### [MEDIUM] — `custom_code` node reported as a `SOURCE` of column data when a last-run `observed` schema is supplied
- **Location:** `emergentflow/research/lineage.py:526` (`trace_column_lineage`)
- **Class:** Logic error / state-consistency (docstring-contract contradiction)
- **Confidence:** Confirmed
- **Description:** In the backward walk, when static resolution returns `None` and the node's
  output column is present in the `observed` mapping, the function marks the node `ColumnRole.SOURCE`
  (detail `"observed in last run (column not statically declared)"`). The module's own docstring
  (lines 475-479) and the inline comment (line 529) explicitly state that `custom_code` "still
  breaks the chain (no upstream) even when observed" — i.e. it must report `UNKNOWN`, never
  `SOURCE`. Only the `observed=None` path honored that; supplying observed columns flipped a
  `custom_code` column into a false data-origin claim.
- **Evidence / Reproduction:**
  ```python
  from emergentflow.nodes import get
  from emergentflow.ir import Graph, Paradigm, Edge, PortRef
  from emergentflow.research.lineage import trace_column_lineage, ColumnRole
  load = get("data.load_csv")().instantiate(label="load")
  custom = get("script.custom_code")().instantiate(label="custom")
  e = Edge(id="e1",
           source=PortRef(node_id=load.id, port_id=[p for p in load.ports if p.name=="frame"][0].id),
           target=PortRef(node_id=custom.id, port_id=[p for p in custom.ports if p.name=="value"][0].id))
  g = Graph(paradigm=Paradigm.FUNCTIONAL, name="cf", nodes={n.id:n for n in (load, custom)}, edges={e.id:e})
  lineage = trace_column_lineage(g, custom.id, "anything", observed={custom.id:["anything"], load.id:["anything"]})
  roles = {n.node_type: n.role for n in lineage.nodes}
  # Before fix: custom_code -> SOURCE (SOURCE present, UNKNOWN absent).
  # After fix:  custom_code -> UNKNOWN.
  ```
  Regression test: `tests/test_research_column_lineage.py::test_trace_column_lineage_custom_code_observed_is_unknown`.
- **Impact:** The canvas/server lineage view can falsely assert that a computed `custom_code`
  column is a genuine data origin whenever last-run observed column names are wired in — exactly
  the flow Epic 18 Story 4 added `observed` for. Wrong provenance metadata misleads data
  trust/audit and downstream impact/lineage rendering.
- **Remediation:** Gate the observed-`SOURCE` branch behind `node.type != "script.custom_code"`
  so a custom-code node falls through to the existing `UNKNOWN` boundary:
  ```python
  elif (
      node.type != "script.custom_code"
      and observed is not None
      and col in observed.get(nid, ())
  ):
      role, source_cols = ColumnRole.SOURCE, ()
  ```

### [LOW] — `kruskal` returns a silently-NaN statistic/p-value when a group has no non-null values
- **Location:** `emergentflow/stats/__init__.py:448` (`kruskal`)
- **Class:** Boundary / empty-input handling (silently wrong result)
- **Confidence:** Confirmed
- **Description:** Samples are built as `g[value_col].dropna().to_numpy()` per group, so a group
  whose `value_col` is entirely NaN yields an **empty** sample array handed to
  `scipy.stats.kruskal`. On the pinned scipy this emits a `SmallSampleWarning`
  ("One or more sample arguments is too small") and returns `NaN`/`NaN` for statistic and
  p-value — no exception, no typed error. The returned `effect_size` is likewise `NaN`. The
  caller gets a meaningless result cell that looks like a real statistical output.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.stats import kruskal
  df = pd.DataFrame({"g": ["a","a","b","b"], "v": [1.0, 2.0, None, None]})  # group 'b' all-NaN
  print(kruskal(df, group_col="g", value_col="v"))
  # Before fix: statistic=NaN, p_value=NaN (scipy SmallSampleWarning), silently.
  # After fix:  raises ValueError "found group(s) with no non-null values in 'v': ['b']".
  ```
  Regression test: `tests/test_stats.py::test_kruskal_group_with_no_non_null_values_raises`.
- **Impact:** A plausible data shape (a group present but with all-missing values) turns the test
  into a quiet NaN row instead of either a valid statistic or a clear message — a silent
  wrong-result on a commonly-dirty column. The two-group healthy path is unchanged (tests confirm
  `statistic`/`p_value` still compute).
- **Remediation:** Detect empty (all-NaN) groups up front and raise a typed, actionable error:
  ```python
  empty_groups = [str(k) for k, g in df.groupby(group_col, sort=True) if g[value_col].dropna().empty]
  if empty_groups:
      raise ValueError(
          f"Kruskal-Wallis found group(s) with no non-null values in {value_col!r}: "
          f"{empty_groups}. Drop or impute those groups before testing."
      )
  ```

### [LOW] — `trace_lineage` / `trace_column_impact` crash with an uncaught `CycleError` on a cyclic graph
- **Location:** `emergentflow/research/lineage.py:204` (`trace_lineage`) and `:693` (`trace_column_impact`)
- **Class:** Control flow / unhandled degenerate input (consistency bug)
- **Confidence:** Confirmed
- **Description:** `Graph`'s structural validator does not reject cycles, so a cyclic (or self-loop)
  graph is constructible. `trace_lineage` and `trace_column_impact` call `topological_sort(graph)`
  bare and raise an uncaught `CycleError` on it, while the sibling `trace_column_lineage` already
  wraps the same call in `try/except` and falls back to insertion order ("A degenerate cycle is
  tolerated" per its comment). Copy-paste inconsistency left the other two entry points crashing.
- **Evidence / Reproduction:**
  ```python
  g = Graph(paradigm=Paradigm.FUNCTIONAL, name="cyc", nodes={n.id:n for n in (n1,n2)},
            edges={"e-ab": e_ab, "e-ba": e_ba})   # n1->n2 and n2->n1
  trace_lineage(g, n1.id)        # Before fix: CycleError; after: returns nodes [n1, n2].
  trace_column_impact(g, n1.id, "col")  # Before fix: CycleError; after: returns impact.
  ```
  Regression tests: `tests/test_research_lineage.py::test_trace_lineage_tolerates_cycle`,
  `tests/test_research_column_lineage.py::test_trace_column_impact_tolerates_cycle`.
- **Impact:** Degenerate-but-constructible graphs crash two lineage endpoints on a pristine graph
  (no `observed`), diverging from `trace_column_lineage`'s documented cycle tolerance and forcing
  callers to defensively wrap a pure API.
- **Remediation:** Apply the same `try/except Exception: order = [...] in <visited>` fallback to
  both functions (the reachability/visited walks above have already bounded the node set, so
  falling back to insertion order only affects presentation, never correctness).

## Notes & unverified leads
- **Stats `_partial_eta_sq_ci` CI-endpoint swap (REFUTED).** Discovered a swap-looking assignment
  (percentile `1 - alpha/2` into `lambda_low`, `alpha/2` into `lambda_high`). A direct
  monotonicity experiment (`scipy.stats.ncf.cdf(5.0, 2, 97, lam)` for `lam` in 0..20 → 0.99..0.08)
  proves the noncentral-F CDF is **decreasing** in λ, so the higher percentile yields the *smaller*
  λ (low endpoint) and the lower percentile the larger λ (high endpoint) — the labels are correct.
  Not a bug.
- **`reduce_dimensions` (`component_1..n`) vs `fit_transform`/`apply_estimator` (`component_0..k-1`)
  naming (demonstrated divergence, NOT changed).** Chaining a PCA `reduce_dimensions` output into a
  PCA `fit_transform` raises a spurious "df already has columns ['component_1']" collision. Genuine
  inconsistency, but both conventions are heavily documented and asserted in existing tests/node
  golden output; standardizing either way is a public-API column-name break. Logged as a design
  decision for a naming-consistency pass rather than changed here.
- **`research/quality._check_regex_match` uses `.str.match` (start-anchored, not full) and
  `astype(str)` turns NaN into `"nan"`. Semantic ambiguity (is a NaN a non-match?) rather than a
  demonstrable wrong output; needs a spec decision on null handling and anchored-vs-full matching.
- **`research/quality` `_check_range` trivially passes when both `min` and `max` are None;**
  `_check_allowed_values` with an empty `values` list flags every row. Both are degenerate-spec
  inputs a well-formed expectation doesn't produce.
- **`eval.score` / `eval.export` raise bare `KeyError`/`TypeError` on malformed specs or
  missing columns rather than a typed error** (e.g. `score()` indexing a nonexistent
  `output_column`). Error-path hardening; Low, would need a guards-first pass to do cleanly.
- **`stats.summaries.mixedlm_fit_stats` takes `cov_re.iloc[0,0]` as the random-intercept variance
  for the ICC;** correct only when the intercept is the first random term. Model-formula-dependent;
  hard to prove a concrete mislabel without a non-intercept-first fit.
- **`git`-style mutation shallow-copy / param alias** in `ir/mutation.py` and
  `codegen/params.py` (returned graph shares unchanged Node objects / override values by reference).
  Matches the Pydantic immutable-by-convention design; the "Never mutates" promises hold. Left as-is.
- **`validity/metrics.py` `RankingMetricsOnRandomSplit` skips whenever *any* temporal split is
  upstream**, potentially missing a genuinely random-held-out evaluate; and
  `RandomSplitOnTemporalGraph` uses a graph-global (not branch-local) temporal signal → possible
  false positives. Rule-scoping semantics, not a data-corrupting defect; deferred.

## Coverage & limitations
- Deep-dive verified and fixed: `research/lineage` custom_code provenance, `random`/kruskal
  empty-group handling, `trace_lineage`/`trace_column_impact` cycle tolerance. Each fixed with a
  regression test.
- Fresh sweeps (leads only, most refuted or noted): `__init__`-level stats (anova/kruskal/mann-
  whitney CI legs), `stats/summaries`, `stats/eda`, `research/quality/reproducibility/report`,
  `eval/{label,run,judge,score,export}`, `data/{http,warehouse,documents}`, `llm/{budget,pricing,
  templating,gateway,replay}`, `clean/{pii,reshape,text_dates,sampling,combine}`, `explain`,
  `viz`, `ir/{mutation,params,serialize,migrate,graph}`, `codegen/params+executor`, `validity`.
- Not re-audited in depth (covered hard by immediately-preceding 2026-08-13/14 hunts):
  `collab/`, main `codegen/{compiler,declarative}`, `server/`, `recommend/`, `timeseries/`,
  `clean/outliers`. The `ui/` canvas is out of scope for this Python-package hunt.
- Gates: full suite **3832 passed, 103 skipped** (4 new regression tests); `ruff check`/`format`
  clean; `mypy` clean (349 source files). No `@public_op` signatures, IR models, node `spec`s, or
  mutation/session-event schemas changed, so no `export_ui_contracts`/`check_ui_boundary` churn
  was required.
