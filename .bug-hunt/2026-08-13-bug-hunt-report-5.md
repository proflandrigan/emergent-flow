# Bug Hunt Report: emergent-flow (independent sweep #5, least-covered surfaces)

## Summary
- Scope reviewed: a fresh independent pass over `emergentflow/` weighted toward the
  under-covered clean/derive, clean/reshaping, research/lineage (multi-hop impact),
  research/reproducibility, stats/diagnostics, and ml/summaries surfaces — deliberately
  avoiding re-hunting the ml-ensemble/stats/recommend/collab surfaces already covered by
  the four same-day reports. The ADR-0002 equivalence gate remains green (331 passed); the
  full suite passes before this hunt (3748 passed, 103 skipped).
- Confirmed findings: 1 High, 4 Medium, 1 Low.
- Overall assessment: The codebase is mature and almost universally defensive, but this
  pass surfaced a silent **under-reporting** bug in `trace_column_impact` (the headline
  blast-radius feature misses transitive impact that flows through a derived column), a
  module-name-vs-column misidentification in the derive provenance parser, boolean→integer
  silent coercion in `clean.derive`, two untyped error leaks through the `ef.stats.diagnostic`
  seam, and a reproducibility seed that is silently dropped. None crash on a common happy
  path; the lineage ones are the most damaging because they return confidently-wrong answers
  for the feature's stated purpose.

## Findings

### High — `trace_column_impact` silently misses impact that flows through a derived column (multi-hop blast radius is wrong)

- **Location:** `emergentflow/research/lineage.py:680` (reach propagation) and `:730-752`
  (derived-column surfacing)
- **Class:** Silent wrong result / under-reported blast radius
- **Confidence:** Confirmed
- **Description:** `trace_column_impact` propagates a seed column forward by computing
  `reach[nid] = _surviving_columns(node, collected)`. For a `clean.derive_column`,
  `_surviving_columns` (`:414-432`) returns the incoming columns unchanged (passthrough),
  and the *derived* output column is only surfaced in the node listing at `:730-752` — it is
  never added back into `reach`. So impact stops one hop past a derive. When the blast radius
  travels *through* a derived column to a further consumer (e.g. `x → y (=x*2) → z (=y+1)`),
  `z` is never reported as impacted by `x`, even though changing `x` changes `z`.
- **Evidence / Reproduction:** a three-node chain
  `load_csv → derive(y=x*2) → derive(z=y+1)`, seeded at `x`:
  ```python
  load=get("data.load_csv")().instantiate(label="load")
  der=get("clean.derive_column")().instantiate(label="der", columns=[{"name":"y","expr":"x * 2"}])
  down=get("clean.derive_column")().instantiate(label="down", columns=[{"name":"z","expr":"y + 1"}])
  edge(load,der); edge(der,down)
  imp = trace_column_impact(graph, load.id, "x")
  ```
  Observed:
  ```
  nodes: [data.load_csv x SOURCE, derive x PASSTHROUGH, derive y DERIVED,
          derive x PASSTHROUGH]      # `down` carries a phantom passthrough `x`
  edges: load.x -> der.x, der.x -> down.x
  # `down.z` is NOT reported impacted       <- WRONG (x->y->z)
  ```
  Two problems: (1) the real transitive consumer `down.z` is missing entirely from the
  blast radius; (2) the node `down` is reported as carrying a passthrough column `x`, but
  `down`'s only output is `z`, so the edge list fabricates a column that does not exist.
- **Impact:** For any impact query whose reach passes through a derive node into a further
  consumer, the answer is silently incomplete — the exact failure mode the feature exists to
  prevent (under-reporting what breaks if a column goes away). Existing regression tests only
  cover a single-hop derive as the immediate consumer, so this gap is not caught.
- **Remediation:** After a `clean.derive_column` node, add its derived column(s) to `reach`
  with the seed-flow association so the blast radius continues. Concretely, in the loop at
  `:671-680`, after computing `reach[nid] = _surviving_columns(...)`, extend it with the
  derived outputs that reference a reaching seed (the same check already used at `:730-752`),
  e.g.:
  ```python
  reach[nid] = _surviving_columns(node, collected)
  if node.type == "clean.derive_column":
      for name, refs in _derived_to_seed_sources(node).items():
          if refs & reach[nid]:
              reach[nid].add(name)   # let the derived column propagate downstream
  ```
  Then drop the phantom passthrough: a derive that produces only derived columns
  (`z=y+1`) should not re-emit the seed `x`. Re-run the chain probe — it should report both
  `der.y` and `down.z` as impacted, with no `down.x` node/edge.

### Medium — `_derive_source_cols` misidentifies a module name as a column reference

- **Location:** `emergentflow/research/lineage.py:289-295`
- **Class:** Logic error / provenance misidentification
- **Confidence:** Confirmed
- **Description:** The parser builds its `called` set only from `ast.Call` nodes whose
  `func` is a bare `ast.Name`. A qualified call like `np.sqrt(c)` has `func == ast.Attribute`,
  so `np` is never added to `called`; the walk then treats the base name `np` as a referenced
  operand column. The docstring explicitly promises to exclude function calls.
- **Evidence / Reproduction:**
  ```python
  from emergentflow.research.lineage import _derive_source_cols
  _derive_source_cols("np.sqrt(c) + a")   # -> ('a', 'c', 'np')   expected ('a', 'c')
  ```
  Public effect (verified): `trace_column_lineage` on a derive `y = np.log1p(x)` fabricates a
  spurious source edge claiming a DataFrame column named `np` feeds the derived column.
- **Impact:** Column lineage reports a phantom source column (`np`) that never existed on the
  source frame, so lineage results contain a non-existent column reference whenever a derived
  expression uses a qualified numpy/scipy/pandas call (extremely common).
- **Remediation:** Treat a `Call` whose `func` is an `ast.Attribute` as a call whose base
  (the module, e.g. `np` in `np.sqrt`) is *not* an operand. Exclude the `.value` of attribute
  calls from `referenced`, e.g. only collect bare `ast.Name` operands that are neither the
  `func` of a call nor the attribute-chain base of a call.

### Medium — `clean.derive` `_case_when` silently coerces boolean literals to integers when mixed with a numeric literal

- **Location:** `emergentflow/clean/derive.py:144-149` (`,153`)
- **Class:** Silent type coercion / wrong result
- **Confidence:** Confirmed
- **Description:** `_case_when` only forces an `object`-dtype (preserving types) when a string
  branch is present (`has_str and has_non_str`). A case-when mixing a boolean `then`/`else`
  with an `int`/`float` literal — but no string — passes through `np.select` untouched, and
  numpy promotes every boolean to `0`/`1`. The same spec with any string branch present
  preserves real booleans, so behavior depends on unrelated presence of a string.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  from emergentflow.clean.derive import derive_column
  df = pd.DataFrame({"score":[85,40,12,60]})
  r = derive_column(df, columns=[{"name":"grade","when":[{"if":"score>=50","then":True}],"else":100}])
  r["grade"].tolist()          # [1, 100, 100, 1]  int64   (True silently becomes 1)
  r["grade"].iloc[0] is True   # False
  import json; json.dumps(r["grade"].tolist())   # '[1, 100, 100, 1]'
  ```
  A boolean flag column is silently turned into an integer column, so downstream
  `is True` checks fail and JSON/CSV export serializes flags as `0`/`1` — even though the
  user wrote `True`/`False`.
- **Impact:** Silent, data-type-changing corruption of boolean flags produced by case-when —
  the value *looks* right (1/0) but has the wrong type, affecting `== True` identity checks
  and cross-system serialization.
- **Remediation:** Extend the type-preserving branch to also force `object` when the branch
  values mix boolean with numeric (i.e. `not isinstance(bool_val, (int, float))`... rather,
  when bools coexist with non-bool scalars). Concretely, treat "any boolean literal present
  alongside any non-boolean scalar" the same as the existing `has_str and has_non_str` case:
  assign into `df[name] = ...` as `object` instead of letting `np.select` upcast bools.

### Medium — `ef.stats.diagnostic` leaks raw `TypeError`/`ValueError` for two reachable edge inputs instead of the typed error

- **Location:** `emergentflow/stats/diagnostics_catalog.py:47-67` (`_vif`) and `:109-125` (`_heteroscedasticity`)
- **Class:** Error handling / untyped exception escaping a documented contract
- **Confidence:** Confirmed
- **Description:** `_vif` passes an explicit `columns` spec straight to
  `sm.add_constant(df[columns]...)` without checking the columns are numeric, so a
  non-numeric column raises a raw `TypeError` from inside numpy. `_heteroscedasticity` passes
  `model.results.model.exog` (a single column for an intercept-only fit) to
  `het_breuschpagan`, which raises a raw `ValueError`. Both surfaces otherwise raise the typed
  `InvalidModelSpecError` for invalid specs — the `diagnostic` seam's own guard path (`:40`,
  `:51`, `:113`) uses it — so these leaks are inconsistent with the family contract.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({"target": rng.normal(size=50), "b": rng.normal(size=50), "cat": ["a"]*50})
  ef.stats.diagnostic(df, diagnostic="vif", spec={"columns": ["b", "cat"]})
  # TypeError: ufunc 'isfinite' not supported for the input types ...
  df2 = pd.DataFrame({"target": rng.normal(size=100)})
  m = ef.stats.fit_model(df2, model="OLS", spec={"target": "target"})
  ef.stats.diagnostic(None, diagnostic="heteroscedasticity", model=m)
  # ValueError: The Breusch-Pagan test requires exog to have at least two columns...
  ```
  (A non-numeric column in VIF, and an intercept-only model in heteroscedasticity, are both
  reachable from real data — categorical columns and single-term models are common.)
- **Impact:** Callers (and the canvas inspector, which surfaces diagnostic errors) receive a
  bare `TypeError`/`ValueError` with no indication of which column/spec was the problem,
  instead of an actionable `InvalidModelSpecError`, and the exception type is not part of the
  documented stats error hierarchy.
- **Remediation:** In `_vif`, validate/filter to numeric columns and raise
  `InvalidModelSpecError` for non-numeric selections (matching the auto numeric-detect path):
  ```python
  num = set(df.select_dtypes(include="number").columns)
  bad = [c for c in columns if c not in num]
  if bad:
      raise InvalidModelSpecError(f"VIF requires numeric columns; non-numeric: {bad!r}.")
  ```
  In `_heteroscedasticity`, guard the intercept-only case (use `exog` sub-selected to the
  regressors, or catch and re-raise as `InvalidModelSpecError`).

### Medium — `capture_run` silently omits non-integer `seed`/`random_state` values, contradicting its contract

- **Location:** `emergentflow/research/reproducibility.py:110`
- **Class:** Broken contract / silent data omission
- **Confidence:** Confirmed
- **Description:** The docstring states seeds are collected for "every node param named
  'seed' or 'random_state' with a non-None value", but the code requires
  `isinstance(param.value, int)`. A valid float seed (e.g. `random_state=42.0`, which fully
  determines the run) is silently dropped from the reproducibility snapshot.
- **Evidence / Reproduction:**
  ```python
  g = Graph(nodes={"n1": Node(id="n1", type="data.csv",
        params=[{"name":"random_state","type_token":"float","value":42.0}])})
  capture_run(g).seeds   # -> {}   (a float seed determining the run is absent)
  ```
- **Impact:** The reproducibility snapshot under-specifies the seeds needed to reproduce a
  run, so a recorded reproducible experiment is silently not reproducible from its snapshot.
- **Remediation:** Collect any non-`None`, numeric/`int()`-coercible seed instead of only
  `int`. E.g. accept `isinstance(param.value, (int, float)) and not isinstance(param.value, bool)`
  (or `number`), so `42.0` and `42` both land in `seeds`.

### Low — `reshape(mode="melt")` leaks an untyped pandas `ValueError` instead of `ColumnCollisionError` on a name collision

- **Location:** `emergentflow/clean/reshaping.py:161-168`
- **Class:** Error contract / untyped exception
- **Confidence:** Confirmed
- **Description:** The melt collision pre-check examines `id_vars` and the `var_name ==
  value_name` case but not a `value_name`/`var_name` colliding with a *melted* `value_vars`
  column. That configuration passes the check and then falls into pandas, which raises a bare
  `ValueError`, inconsistent with the typed `ColumnCollisionError` the sibling verbs use.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({"id":[1,2,3],"a":[10,20,30],"b":[5,6,7]})
  reshape(df, mode="melt", id_vars=["id"], value_vars=["a","b"], value_name="b")
  # -> ValueError: value_name (b) cannot match an element in the DataFrame columns.
  #    (not ColumnCollisionError)
  ```
- **Impact:** Design/get-type misses: error handling on the reshape path by contract
  (`ColumnCollisionError`) silently bypasses for this collision shape; callers that catch
  the typed error miss this one.
- **Remediation:** Extend the pre-check to reject `value_vars`-column collisions before
  calling pandas, raising `ColumnCollisionError` with the same message the family uses.

## Notes & unverified leads
- **`trace_lineage` (node-level) crashes on cyclic graphs** (`emergentflow/research/lineage.py:204`)
  while `trace_column_lineage` guards against cycles — reproduced a `CycleError`, but graph
  construction appears to validate acyclic, so likely unreachable (would need a cycle to slip
  past validation). Unconfirmed as a reachable defect.
- **`ml/summaries.py:30` single-return-path 0-d `coef_` iteration** — a scalar `coef_` would
  raise `TypeError`, but no real fitted sklearn estimator exposes a 0-d `coef_`; unverifiable
  on real models.
- **`data/documents.py:145-153` doc_id collision** — `doc_id = file_path.stem`, so `notes.txt`
  and `notes.md` in one directory collide; deducible from the code but not exercised (avoids
  file creation).
- **`stats` VIF constant-column → `0.0` "ok"** — a constant numeric column reports VIF `0.0`
  (flagged "ok") instead of near-infinite; originates inside statsmodels, needs a product
  decision on whether to pre-drop constants.
- **Bayesian summaries (`summaries.py:145`, `:178`) narrow indexing** (`hdi_cols[0:2]`,
  `next(iter(observed_data.sizes))`) — arviz/pymc not installed in this venv, so not
  executable here.

## Coverage & limitations
- Focused on the least-hunted surfaces; the ml-ensemble, stats-op, recommend, collab, clean
  outlier/explode/encode, codegen and UI surfaces covered by the four same-day earlier
  reports and prior hunts were not re-reviewed.
- All findings reproduced against isolated synthetic inputs with `uv run python` on the
  current branch; full suite (3748 passed) and ADR-0002 equivalence (331 passed) are green —
  these are behavior gaps not covered by the existing tests.
- I did not run the `[bayes]`/`[embed]`/`[recommend]` optional-extra paths (deps absent);
  several arviz-driven leads are therefore unverified, not cleared.