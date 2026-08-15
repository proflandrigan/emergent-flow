# Bug Hunt Report: emergentflow (Python package)

- **Date:** 2026-08-14
- **Branch:** `feat/agent-onboarding-and-oom`
- **Team:** Bug-Hunt skill (Discovery → Verify → Report loop)

## Summary
- Scope reviewed: `emergentflow/ir/mutation.py`, `emergentflow/server/cache.py`, and re-sweeps of
  `clean/` (outliers, derive, sampling, reshaping, text_dates, pii, combine), `reports/`,
  `research/report.py`, `collab/` (digest, knowledge, budget_gate, consult, checkpoints, gates),
  `codegen/` (declarative, executor, traversal, wiring), `eval/judge.py`, `ml/`, and
  `connections/profiles.py`. UI excluded.
- Confirmed findings: 1 High, 1 Low. Both reproduced with concrete evidence, fixed, and pinned by
  regression tests.
- Overall assessment: The package is in healthy shape (3821 passing pre- and post-hunt; ruff/mypy
  clean; ADR-0002 equivalence green). The two confirmed defects are narrow but real: the graph
  mutation protocol silently dropped graph-level `params` — a data-loss bug on a feature added in
  issue #116 that every agent/accepted proposal would have triggered — and the durable execution
  cache could never re-attain its size cap once orphaned `.meta.json` sidecars accumulated. A third
  lead (outlier bounds NaN on extreme ~1e308 magnitudes) was demonstrated but not promoted to a
  finding because its trigger is degenerate and a sound fix would require reimplementing numeric
  primitives.

## Findings

### [HIGH] — `apply_mutation` silently drops graph-level `params`
- **Location:** `emergentflow/ir/mutation.py:207-214`
- **Class:** State consistency / dropped field / silent data loss
- **Confidence:** Confirmed
- **Description:** When `apply_mutation` reconstructs the result `Graph`, it forwards
  `schema_version`, `paradigm`, `name`, `nodes`, and `edges` but omits `graph.params`. `Graph.params`
  (issue #116 graph-level params, e.g. `{"epochs": {"name": "epochs", ...}}`) defaults to `{}` in the
  model, so every call to `apply_mutation` — even a no-op proposal or a `set_params` that touches only
  node params — rebuilds a graph with all graph-level params erased. The collab `accept_proposal` path
  and the `consult`/`run_consult` set_params mutations both flow through this function, so accepting a
  single agent-authored change on a graph that carries graph-level params wipes them with no error.
- **Evidence / Reproduction:**
  ```python
  from emergentflow.ir.graph import Graph
  from emergentflow.ir.node import Node, Position
  from emergentflow.ir.params import Param
  from emergentflow.ir.mutation import GraphMutation, apply_mutation
  g = Graph(name="g", paradigm="functional",
            nodes={"a": Node(id="a", type="map", position=Position(x=10, y=10))},
            params={"epochs": Param(name="epochs", type_token="int", value=10, default=1)})
  m = GraphMutation(base_version=0, add_nodes=[Node(id="n2", type="map", position=Position(x=50, y=50))])
  res = apply_mutation(g, m)
  print(res.params)   # {} before the fix; {"epochs": Param(...)} after
  ```
  Observed: `res.params == {}` while `g.params` was `{"epochs": ...}`. After the fix, `res.params ==
  g.params`. Regression tests: `TestApplyMutationPreservesGraphParams.test_graph_level_params_survive_a_mutation`
  and `test_graph_level_params_survive_a_noop_mutation`.
- **Impact:** Any agent/session mutation accepted on a graph with graph-level params silently deletes
  them (optimizer epochs, learning rate, split seeds set at the graph level), producing graphs that
  behave differently than the author configured — a quiet, deterministic data-loss defect on the
  collaboration path.
- **Remediation:** Forward the field when building the result:
  ```python
  result = Graph(
      schema_version=graph.schema_version,
      paradigm=graph.paradigm,
      name=graph.name,
      nodes=new_nodes,
      edges=new_edges,
      params=graph.params,
  )
  ```

### [LOW] — Cache eviction can never restore the size cap when orphaned `.meta.json` sidecars accumulate
- **Location:** `emergentflow/server/cache.py:126-150`
- **Class:** Resource management / stale state / eviction boundary
- **Confidence:** Confirmed
- **Description:** `_evict_to_cap` sizes the cap from `total_bytes()`, which sums *every* file in the
  cache dir including `.meta.json` sidecars, but only ever shrinks by removing `.pkl`-keyed entries
  (`while len(pkl_paths) > 1 and total_bytes() > max_bytes`). An orphaned `.meta.json` (a sidecar whose
  `.pkl` was lost or removed out-of-band) therefore inflates `total_bytes` forever: once one (or zero)
  `.pkl` remains the loop condition `len(pkl_paths) > 1` stops it, so the cache stays over `max_mb`
  indefinitely — a permanent, silent cap violation.
- **Evidence / Reproduction:**
  ```python
  c = ExecutionCache(root=tmp, max_mb=0.0001)          # ~104-byte cap
  c.put("bbb", {"x": "z"*100}, node_id="n", label="l") # one artifact kept
  for i in range(5): (tmp / f"orphan{i}.meta.json").write_text('{"x":' + '1'*120 + '}')
  c.put("aaa", {"x": "y"*200}, node_id="n", label="l") # triggers an eviction pass
  total = sum(p.stat().st_size for p in tmp.iterdir() if p.is_file())
  total > c._max_mb*1024*1024                          # True BEFORE the fix: 839 > 104
  ```
  Before the fix `total_bytes` stayed 839 > 104 with the orphans present; after the fix the orphan
  sidecars are removed and the cap is restored. Regression: `test_eviction_cleans_orphaned_meta_sidecars`.
- **Impact:** A long-running server with a modestly-sized cache can exceed its configured `--cache-max-mb`
  and never reclaim the disk, degrading over time. Narrow trigger (orphaned sidecars are rare), hence Low.
- **Remediation:** After the eviction loop, garbage-collect sidecars that have no live artifact. Any
  `.meta.json` without a sibling `.pkl` is unreadable (nothing reads a meta without its artifact) and
  contributes nothing to the cap's intent, so it can be removed without affecting valid entries:
  ```python
  for meta in self._root.glob("*.meta.json"):
      if not self._pkl_path(meta.name[: -len(".meta.json")]).is_file():
          meta.unlink(missing_ok=True)
  ```
  (Note: must strip the `.meta.json` suffix from the basename, not `Path.stem`, since
  `Path("a.meta.json").stem == "a.meta"`.)

## Notes & unverified leads
- **Outlier detector fails on near-`float64`-max magnitudes (confirmed, not promoted).** Demonstrated
  that `detect_outliers(df, columns=["v"], method="zscore")` on `[1e308]*n, -1e308` returns
  `is_outlier=False` for every row and `outlier_score=NaN`; root cause is float64 mean/std-aggregation
  overflow in `numpy` (`RuntimeWarning: overflow encountered in reduce`), which already corrupts the
  bounds to `(nan, inf)` at `~8e307`. Left as a note rather than a finding because the trigger requires
  values at the extreme of the `float64` range (real-world impact negligible) and a sound fix means
  reimplementing overflow-safe mean/std — invasive and regression-risky for a degenerate input.
- **`EMERGENTFLOW_BUDGET_CEILING_USD` swallows parse errors** (`budget_gate.get_budget_ceiling`): a
  typo'd/non-numeric value silently falls back to the $1.00 default, and a *negative* value is accepted
  and blocks every run. Inconsistent with `EMERGENTFLOW_EST_COST_PER_CALL`, which is parsed
  unguarded (a bad value crashes). Marginal whether choking on config is preferable to failing safe;
  not promoted.
- **`knowledge.py` temp-file race / un-wrapped `JSONDecodeError`** (two writers sharing the `.tmp`
  path; a hand-corrupted `knowledge.json` raising a raw error at store init) — require processes
  sharing a path or a corrupted file, and the fix's preferred behavior is debatable; not promoted.
- **`parse_dates` / `clean_text` boundary** — `pandas` `OutOfBoundsDatetime` is a `ValueError`
  subclass, so it is already caught and wrapped in `CleanError` (refuted by repro). `derive._case_when`
  missing-`else`→`None` and `sample_rows` per-group identical `seed` are documented/defensible behavior.
- **`cache.py` `sdk_version` recorded-but-not-validated on read** — the cache is caller-hash-keyed and
  best-effort; version-pinning the read would be a design change, not a defect. Not promoted.

## Coverage & limitations
- Deep-dive on `ir/mutation.py` and `server/cache.py` (both fixed with regression tests); targeted
  sweeps of `clean/`, `collab/`, `codegen/declarative `, `eval/judge.py`, `ml/`, `reports/`,
  `research/report.py`, and `connections/profiles.py`. Not re-audited: the `ui/` canvas and the
  effectful driver layers (`data/warehouse/`, `llm/` gateway) that were heavily covered by the
  immediately-preceding 2026-08-13/14 hunts.
- The outliers lead is documented rather than fixed for the reasons above; a future hunt focused on
  numerical robustness at scale should revisit it.
- Gates: full suite 3821 passed, `ruff check`/`format`, `mypy`, and the ADR-0002 equivalence gate
  (331 passed) all green after the fixes.
