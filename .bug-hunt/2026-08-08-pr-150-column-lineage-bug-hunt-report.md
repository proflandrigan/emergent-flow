# Bug Hunt Report: PR #150 — Column-Level Lineage (Epic 18, issue #128)

## Summary

- **Scope reviewed:** the full PR #150 diff (64 files, 2191 +/ 50 −) — `emergentflow/research/lineage.py` (column model + `trace_column_lineage`/`trace_column_impact`), `emergentflow/server/service.py` (`column_lineage_for`, `_observed_columns`), `emergentflow/validity/rules/leakage.py` (`target_derived_feature` rewrite), the `column_effect` node declarations, the coverage gate, and the UI (`ColumnLineagePanel`, `PayloadView`, `Inspector`, `vite.config.ts`). Not re-reviewed: the pre-existing node-level `trace_lineage` (unchanged), the full `ml`/`stats`/`viz` node internals it touches only via declarations, and the generated snapshot/catalog artifacts (verified in sync, not logic).
- **Confirmed findings:** 1 Medium, 1 Info. (Two further Medium bugs found in the same hunt were fixed and committed on the branch before this report: impact reach propagation through `select_columns` drops, and case-when derive lineage not walking `when` conditions.)
- **Overall assessment:** The core is well-engineered — pure, deterministic, cycle-safe, honest `unknown` boundaries, and the ADR-0002/leakage invariants hold. The real defects cluster in the **impact analysis** (`trace_column_impact`), where the reach/edge bookkeeping around column-dropping nodes and the derived-column special case were not fully consistent with the lineage walk. The coverage gate also overstates how many declared nodes actually trace.

## Findings

### Medium — `trace_column_impact` emits passthrough edges for columns the target node drops

- **Location:** `emergentflow/research/lineage.py:756-771` (the edge-emission loop in `trace_column_impact`)
- **Class:** State & consistency / logic error (edge list contradicts node list)
- **Confidence:** Confirmed
- **Description:** After the reach propagation was filtered through `_surviving_columns` (so `reach[nid]` correctly omits a seed column a node drops), the *edge* emission loop was not updated to match. It iterates `for sc in sorted(reach[src])` and emits a `PASSTHROUGH` edge from `src` into `nid` for **every** column in the source's reach — even when that column does not survive `nid`'s output. The node list therefore reports the node as a dead-end (`UNKNOWN`, empty column) while the edge list claims the seed column flows into it.
- **Evidence / Reproduction:**
  ```python
  # load -> derive(revenue_log=log1p(revenue)) -> select(keep=[revenue_log, user_id])
  impact = trace_column_impact(graph, load.id, "revenue")
  # BEFORE the fix, impact.edges contained:
  #   load.revenue -> derive.revenue   (correct)
  #   derive.revenue -> select.revenue (WRONG: select drops `revenue`)
  ```
  Observed: `select` appears in `impact.nodes` as `UNKNOWN` with `column=""` (its output has no `revenue`), yet `impact.edges` still contained `derive.revenue -> select.revenue`. The two lists disagreed about whether `revenue` reaches `select`. Confirmed with the probe in `/tmp/opencode/hunt1.py`.
- **Impact:** Blast-radius consumers see a spurious edge claiming a dropped column still flows into a downstream node, inflating the reported reach of a source column. Not a crash, but a correctness/consistency defect in the headline "what breaks if this goes away" answer (Epic 18 Story 6).
- **Remediation:** Intersect the emitted columns with the target's surviving reach so an edge is drawn only for a column present on the target's output:
  ```python
  for sc in sorted(reach[src] & reach[nid]):
      edges.append(ColumnLineageEdge(source_node_id=src, source_column=sc,
          target_node_id=nid, target_column=sc, role=ColumnRole.PASSTHROUGH))
  ```
  Re-run the probe: the only edge is now `load.revenue -> derive.revenue`. Fixed + regression-tested in `tests/test_research_column_lineage.py` (`test_trace_column_impact_edges_require_surviving_column`, and the edge assertion in `test_trace_column_impact_stops_at_select_drop`), committed as `8fadc90`.

### Info — The column-effect coverage gate overstates real traceability

- **Location:** `scripts/check_column_effect_coverage.py:31-45`; `emergentflow/research/lineage.py:358-410` (`_resolve_column`)
- **Class:** Misleading metric / dead declaration
- **Confidence:** Confirmed (as a metric inaccuracy, not a runtime failure)
- **Description:** The coverage report counts a node as "declared" if `column_effect is not None`, but `_resolve_column` only honors `SOURCE` and `PASSTHROUGH` kinds plus two hardcoded special cases (`clean.select_columns`, `clean.derive_column`). The other declared kinds — `DERIVE`, `ENCODE`, `AGGREGATE`, `CUSTOM`, `SELECT` — are advisory catalog metadata the tracer ignores; any column traced through such a node reports `UNKNOWN`. So the 27% "declared" figure overstates the fraction of nodes whose columns actually trace.
- **Evidence / Reproduction:**
  ```python
  # transform.discretize is declared column_effect=DERIVE
  t = trace_column_lineage(graph, disc.id, "age")
  for n in t.nodes: print(n.role)   # -> ColumnRole.UNKNOWN  (not DERIVED)
  ```
  Counted across the registry: 39 nodes declared, but only 28 actually resolve in `_resolve_column` (11 declared-but-unresolved: `transform.encode_categorical`, `stats.group_by_aggregate`, `clean.explode_lists`, `clean.reshape`, `clean.concat`, `clean.fuzzy_join`, `clean.merge`, `clean.semi_join`, `transform.discretize`, `transform.generate_features`, `transform.detect_outliers`). Many of these are not `frame`-output nodes at all (e.g. `encode_categorical` outputs `transformer`/`result`; `group_by_aggregate` outputs `summary`), so `unknown` is the *honest* answer — the defect is that the gate counts them as "declared" success.
- **Impact:** The CI gate (`--min-pct 20` passes at 27%) and the DoD's coverage framing imply a lineage quality that doesn't exist for those 11 nodes, so coverage can look healthy while real traceability is ~19%. A future node added with a cosmetic `DERIVE`/`CUSTOM` declaration silently improves the "declared" number without making anything traceable.
- **Remediation:** Have the gate report (and gate on) the *resolvable* fraction — count only kinds `_resolve_column` actually honors plus the two special-cased types — or print both numbers ("declared vs. resolvable"). Whichever is chosen, the report should stop presenting non-resolved kinds as traceability. This is a reporting/metric decision the maintainer should make; left unremedied in this hunt.

## Notes & unverified leads

- **`_observed_columns` reads the latest run regardless of graph match** (`emergentflow/server/service.py:1270-1300`). It unconditionally reads the newest saved run's payloads and keys observed columns by `node_id`. If the last run was a different graph that happens to reuse a `node_id`, the refinement could attribute the wrong columns. Not promoted to a finding: I could not construct a case where this produces a *wrong lineage answer* without contriving a mismatched run, and the "observe the last run" behavior is the documented Story-4 design. Would need a concrete stale-run repro to confirm.
- **`_frame_predecessor` assumes the first IN port is the table** (`emergentflow/research/lineage.py:325-350`). Verified every currently-declared passthrough/SOURCE node has `frame` as its first IN port, so nothing bites today. Latent fragility: a future passthrough declaration on a node whose first IN port is not the frame (e.g. a `model` port) would silently trace the wrong predecessor. Worth a comment/guard when adding new passthrough declarations.
- **Impact seeds from a DERIVED column are labeled `SOURCE`** in `trace_column_impact` (`lineage.py:~650`). Tracing impact of a derived output column marks the originating node `SOURCE`. Cosmetic role mislabel; omitted as a finding because it doesn't change the reach.
- **`vite.config.ts` adds both `/lineage` and `/lineage/column`** (`ui/vite.config.ts:17-18`). The `/lineage` entry is a prefix of `/lineage/column`, so the latter is effectively dead (both proxy to the same backend). Harmless — both target `127.0.0.1:8765` — and adding `/lineage` actually fixes a pre-existing dev-proxy gap for the node-level `LineagePanel`, so this is net-positive, not a defect.

## Coverage & limitations

Verified with local probes and the existing suite (full lineage/validity/server column-lineage tests: 52 passed; `mypy` clean on 333 files; `ruff check`/`format` clean on all touched files). I did not re-run the full 3600-test suite this hunt (it was green in the preceding review pass and this hunt changed only lineage internals + tests). The UI was reviewed by reading (`ColumnLineagePanel`, `PayloadView`, `Inspector`, `vite.config.ts`) and the existing vitest file; no UI code was modified. The two Medium bugs found and fixed earlier in this same hunt (impact reach through `select_columns` drop; case-when derive provenance) are committed on the branch (`adb8f97`) and their regression tests are in `tests/test_research_column_lineage.py`.