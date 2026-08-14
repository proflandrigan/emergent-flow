# Memory & Scale Remediation

The in-process synchronous executor means a single node's allocation spike can OOM-kill the
whole `emergentflow serve` process and every session (sessions are in-memory). This documents
the known hotspots, the audits that were done, and the remediation strategy — both what is now
adopted and what is planned.

## The failure mode

- One graph node runs synchronously inside the server process (compile_to_code/execute run in-process; no Celery/Redis/sandboxing). A single dense n×n (or n²) allocation in a fit can exhaust RAM and trigger SIGKILL, taking down every session and the canvas.
- Session state is in-memory (`SessionStore`), so an unexpected process death loses in-progress graphs.

## Known hotspots (verified against current HEAD)

- recommend KNN fitters (`emergentflow/recommend/catalog.py`, `_fit_item_knn_cf` / `_fit_user_knn_cf`): previously materialized dense n×n similarity + common-count + top-k arrays. **Remediated (Task 9):** now computed block-wise via `_build_knn_similarity`, peak memory is one `(block_rows × n)` block; a pre-flight guard (see below) refuses fits whose n² footprint would exceed a cap.
- recommend `evaluate`/`compare` diversity metric (`emergentflow/recommend/__init__.py`): previously an all-pairs O(U²) loop over users. **Remediated (Task 10):** `_bounded_diversity` compares a deterministic sample of users beyond `_DIVERSITY_SAMPLE_SIZE`; `compare` gained a `metrics` param defaulting to seven cheap metrics (dropping quadratic `diversity`).
- stats `correlation` (`emergentflow/stats/__init__.py`, ~line 925): `df.corr()` builds a dense D×D matrix for D numeric columns — O(D²), a real hotspot for very wide inputs.
- stats `co_missingness` (`emergentflow/stats/eda.py`, ~line 121): a nested per-column pair dict building a dense D×D matrix — O(D²).
- recommend `co_occurrence` fit (`emergentflow/recommend/catalog.py`, ~line 512): computes `(binary.T @ binary).tocsr()` — the scipy sparse product stays sparse, but a dense catalog's pair nonzeros can grow; keep CSR, avoid `.todense()`.
- content-based `tfidf_similarity` (~line 773) and `feature_knn`/`NearestNeighbors` (~line 867): a single query against M items is fine; embedding matrices grow with row count but are not n×n.
- `embed.text` with a local `sentence-transformers` model: encodes N rows → memory grows linearly with N; large corpora may need chunking.
- General grep targets audited: `.todense()`, `fill_diagonal`, `cosine_similarity` over big matrices, `np.zeros((n,n))`/`np.eye`/`np.ones((m,m))` (dense square), nested per-column loops, `pd.concat` in loops, `np.linalg.svd`/`eigh` over large dense inputs.

## Remediation strategy

### Adopted (merged in Tasks 9-11)
- Block-wise top-k sparse similarity for KNN fitters (bound peak to one block).
- Bounded/approximate system metrics: deterministic `diversity` sampling + `compare` `metrics` override.
- A typed pre-flight memory guard on the KNN fit path (this task) that estimates the n² footprint and raises `RecommendationScaleError` above a configurable cap rather than letting the process OOM.

### Proposed (documented, not yet implemented)
- **Pre-flight guards** in other O(D²) paths (correlation, co_missingness) — estimate D² and warn/refuse or require an explicit opt-in. Design: shared helper + typed error, default cap, `OPT_IN`/cap param, mirror the recommend guard.
- **Subprocess / worker isolation** with a memory ceiling so one node's blowup returns an error status instead of killing the server and other sessions (this is the long-term fix; aligns with Epic 6 sandboxing). It should live behind the executor seam (`emergentflow.codegen`), not inline in `execute`/`compile_to_code` (which must stay pure).
- **Session persistence / snapshots** to disk so an unexpected process death doesn't lose in-progress graphs (ties to the run/`RunStore` persistence added for issue #8).
- **Multi-model compare at scale:** because `compare` runs each candidate's `evaluate`, the Task 10 `metrics` default (seven cheap metrics) + Task 9 sparse KNN fit combine so several recommenders can be fit and compared on one canvas; default `compare` to per-model top-k evaluate, and run the full bounded metric set only when explicitly requested.

## Pre-flight memory guard (recommend KNN)

`RecommendationScaleError` (a new typed error) is raised by the guard in `emergentflow/recommend/catalog.py` when the estimated dense n×n similarity footprint exceeds `max_footprint_bytes`. The estimate is conservative: it reflects the dense n×n ndarray the block-wise code avoids, so refusing above the cap prevents an OOM on the caller's hardware while still allowing the block-wise path to run for the sizes the guard permits. The default cap is 2 GiB; callers can pass `max_footprint_bytes` (unit: bytes) or set it to a large number to effectively disable. Params flow: `params.get("max_footprint_bytes")`.

## Triage table

| Hazard | Family / node | Severity | Fix | Tracked as |
|---|---|---|---|---|
| Dense n×n similarity/common/top-k | recommend item/user KNN | High | Block-wise top-k sparse + pre-flight guard | Task 9 / 11 |
| Diversity O(U²) all-pairs | recommend evaluate/compare | High | Deterministic sampling + compare metrics default | Task 10 |
| Dense D×D correlation | stats.correlation | Medium | Pre-flight D² guard (proposed) | proposed |
| Dense D×D co_missingness | stats.co_missingness | Medium | Pre-flight D² guard (proposed) | proposed |
| Sparse-but-growing item-pair product | recommend co_occurrence | Low | Keep CSR; avoid .todense() | proposed |
| Embedding matrix of N rows | embed.text | Medium | Chunking for large corpora | proposed |