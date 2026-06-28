# The Acceptance Demo

**What the app can do today.** This document describes the canonical end-to-end pipeline that supersedes the original hardcoded 5-node vertical slice as the reference usable example. The vertical slice still exists as a contract-by-construction proof; the acceptance demo is the practical, demoable pipeline.

## The Pipeline

The acceptance demo is an 8-node FUNCTIONAL pipeline that spans five node families (`data`, `clean`, `ml`, `stats`, `reports`) and exercises the structural novelty of Story 7: a **`Model`-bearing edge** from a trained regressor to an evaluation node.

```
load_sample(diabetes) ─→ drop_missing ─→ select_columns
                                            ├─→ train_test_split
                                            │     ├─→ (train) train_regressor ──(model)──→ evaluate
                                            │     └─→ (test) ───────────────────────────→ evaluate
                                            ├─→ stats.describe
                                            └─→ reports.generate_html_summary
```

This pipeline goes **beyond the original five nodes**, pulling from multiple families and demonstrating how a fitted model ports from one stage to evaluation — a validation gate that ensures the type system and structural wiring keep the graph sound.

## Where It Lives

- **`examples/acceptance_demo/pipeline.json`** — the IR graph in canonical form, generated and validated by the test suite.
- **`examples/acceptance_demo/demo.py`** — the runnable worked example. The `run(output_dir=...)` function executes the full pipeline and returns a summary dict with keys: `r2`, `mae`, `n_test`, `n_rows`, `describe_rows`, `report_path`. It writes `report.html` to the specified output directory.
  - **One-liner:** `python examples/acceptance_demo/demo.py`

## How It's Verified

Three gates enforce correctness:

1. **Structural tests** in `tests/test_acceptance_demo.py` — validate the graph's shape, node types, and edge wiring.
2. **End-to-end demo tests** (also in `tests/test_acceptance_demo.py`) — run the pipeline directly and verify that the summary dict has the expected keys and reasonable metric bounds.
3. **ADR-0002 equivalence test** in `tests/test_codegen_equivalence.py` — the `test_acceptance_demo_equivalence` test proves that `ef.compile_to_code(graph)` and `ef.execute(graph)` produce equivalent results across the whole pipeline, including the `Model`-bearing edge. This is the hard invariant that keeps code generation and in-process execution in sync.

## Canvas Round-Trip

The same graph loads in the canvas palette (via `ef.export_catalog()`), compiles through the `/compile` endpoint to downloadable Python, and executes via `/execute` with real-time per-node status — the data-driven catalog path shipped in Stories 2–6.
