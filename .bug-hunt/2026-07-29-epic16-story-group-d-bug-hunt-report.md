# Bug Hunt Report: Epic 16 Story Group D — research & reproducibility (commit a6cd1db)

## Summary
- Scope reviewed: the full diff of commit `a6cd1db` ("feat(research): Epic 16 Story group D —
  research & reproducibility") — `emergentflow/research/` (`report.py`, `lineage.py`,
  `reproducibility.py`, `quality.py`, `errors.py`), `emergentflow/data/documents.py`,
  `emergentflow/clean/pii.py`, the `detect_schema_violations` extraction in
  `emergentflow/data/contract.py`, `emergentflow/codegen/export.py`'s `export_report`, every new
  reference node (`build_report`, `assert_data`, `data_dictionary`, `load_documents`,
  `redact_pii`) and its codegen/execute pair for ADR-0002 equivalence, `emergentflow/stats/eda.py`'s
  `data_dictionary`, the new `/lineage` server route, the checked-in PDF fixture
  (`tests/fixtures/documents/sample.pdf`), and the `__init__.py`/type-catalog/`pyproject.toml`
  ordering and metadata changes. Focus areas per the task brief: `_chunk_text`'s sliding-window
  math, the PDF fixture's real parseability, the PII regex patterns and the presidio
  monkeypatched test's fidelity, `quality.py`'s `row_count`/`range`/NaN handling,
  `detect_schema_violations`'s message-text parity with pre-refactor `validate_schema`,
  `report.py`'s HTML escaping, `reproducibility.py`'s content-hash determinism and
  `SEED_PARAM_NAMES` matching, and every node's codegen/execute equivalence.
- Confirmed findings: 3 Low/Medium (a chunking off-by-one/boundary bug, a message-text dedup
  regression, and a docstring/behavior mismatch in `export_report`'s filename fallback).
- Overall assessment: the changeset is solid overall — every ADR-0002 codegen/execute pair
  checked was equivalent by construction (both paths route through the same `ef.*` wrapper with
  identical arguments), the HTML report renderer escapes user content correctly (verified no XSS
  gaps in `_escape`/`_render_markdown_block`/`_render_section_html`), the checked-in PDF fixture
  parses correctly with a real pypdf install, `trace_lineage`'s deferred-import fix for the
  circular-import bug is legitimate, and the PII regexes' documented "false positives/negatives
  are expected" disclaimer holds for everything found (no pattern fails to compile or
  contradicts its stated vocabulary). The three confirmed bugs are all boundary/edge-case
  defects in code paths that had thin or no direct unit-test coverage — exactly the kind of gap
  the delegation-risk note flagged. All three are now fixed, verified, and pushed as commit
  `14455ae`.

## Findings

### Medium — `_chunk_text`'s sliding window produced a redundant trailing chunk
- **Location:** `emergentflow/data/documents.py:69-72` (pre-fix), `_chunk_text`
- **Class:** Boundary / off-by-one error
- **Confidence:** Confirmed
- **Description:** The loop condition was `while start < n`, which only checks whether the
  *start* of the next window is still inside the text — not whether the *current* chunk already
  reached the end of the text. Whenever a chunk's end already covered the remainder of the text
  but `start + step` was still `< n` (which happens for any text whose length falls in the
  window `(chunk_size - chunk_overlap, chunk_size]` measured from some chunk's start — a common
  case for short documents, not just a contrived one), the loop ran one more iteration and
  appended a final chunk that was a pure substring of content the previous chunk already
  contained.
- **Evidence / Reproduction:**
  ```python
  from emergentflow.data.documents import _chunk_text
  _chunk_text("x" * 8, chunk_size=10, chunk_overlap=5)
  # before fix: ['xxxxxxxx', 'xxx']  -- second chunk is fully redundant with the first
  # after fix:  ['xxxxxxxx']
  ```
  Also verified against `n=910, chunk_size=1000, chunk_overlap=100` (single chunk, was
  previously producing 2 with the tail wholly contained in the first).
- **Impact:** `ef.data.load_documents` (and the `data.load_documents` node) silently emitted
  duplicate/redundant chunks into the `DocumentFrame` for any document whose length landed in
  that window relative to any chunk boundary. Since this loader's output is documented to feed
  Epic 11's retrieval surface, redundant chunks would pollute retrieval results with duplicate
  content.
- **Remediation applied:** Track each chunk's `end = start + chunk_size`; break out of the loop
  once `end >= n` (the current chunk already reaches the end of the text), instead of relying
  solely on `start < n` to decide whether to continue.

### Low — `detect_schema_violations` extraction dropped column-name dedup in the error message
- **Location:** `emergentflow/data/contract.py:127` (pre-fix), `validate_schema`
- **Class:** Regression / message-text parity break
- **Confidence:** Confirmed
- **Description:** The commit's docstring explicitly claims `validate_schema`'s raised message
  text is byte-identical to before the `detect_schema_violations` extraction. Before the
  refactor, the "present columns" list was built from `sorted(set(frame.columns))` (deduping via
  an intermediate `set`). After the refactor, `validate_schema` builds it directly from
  `sorted(frame.columns)` with no dedup. For a `DataFrame` with duplicate column names, this
  changes the reported "present columns" list from deduplicated to one entry per duplicate.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd
  df = pd.DataFrame([[1, 2, 3]], columns=["a", "a", "b"])
  sorted(set(df.columns))  # old behavior: ['a', 'b']
  sorted(df.columns)       # new (pre-fix) behavior: ['a', 'a', 'b']
  ```
- **Impact:** Low likelihood (duplicate-named columns are an unusual but real pandas edge case,
  e.g. after certain merges without suffixes) but a direct, provable contradiction of the
  commit's own "byte-identical" claim, and a misleading error message when it does occur.
- **Remediation applied:** Restored the dedup: `sorted(set(frame.columns))`.

### Low — `export_report`'s blank-title fallback filename didn't match its docstring
- **Location:** `emergentflow/codegen/export.py:52-67,155` (pre-fix), `_slug_filename` /
  `export_report`
- **Class:** Docstring/behavior mismatch
- **Confidence:** Confirmed
- **Description:** `export_report`'s docstring states the output filename "Defaults to a slug of
  `report.meta.title`, or `'report'` if blank." It reused the pre-existing `_slug_filename`
  helper (originally written for `export_script`'s `.py` module naming) unchanged, whose
  empty-slug fallback is hardcoded to `"pipeline"`. So a `Report` with a blank/whitespace-only
  title was written to `pipeline.html`, not `report.html` as documented.
- **Evidence / Reproduction:**
  ```python
  from emergentflow.research.report import Report, ReportMeta
  from emergentflow.codegen.export import export_report
  report = Report(meta=ReportMeta(title=""), sections=[], html="<html></html>")
  export_report(report, "/tmp/x")
  # before fix: ReportExportResult(html_path=.../pipeline.html, ...)
  # after fix:  ReportExportResult(html_path=.../report.html, ...)
  ```
- **Impact:** Low (requires a caller to build a `Report` with a blank title and no explicit
  `name=`, which `test_research_report.py`'s existing tests never do) but a confirmed,
  reproducible contradiction between documented and actual behavior.
- **Remediation applied:** Gave `_slug_filename` a `default: str = "pipeline"` keyword parameter
  so each caller supplies its own fallback; `export_report` now passes `default="report"`.

## Notes & unverified leads (optional)
Leads investigated and explicitly **not** treated as findings (either refuted or too low-value
to fix given the codebase's own "best-effort" disclaimers):
- `clean/pii.py`'s phone regex false-positives on bare 10-digit numbers (e.g. `1234567890`), and
  leaves a stray `(` when redacting `(555) 123-4567`. Both are explicitly covered by the
  module's own docstring ("false positives/negatives are expected and acceptable for a
  first-pass redaction gate"), and category-application order (email → phone → ssn →
  credit_card) does not corrupt SSN detection — verified with a mixed-category input.
- `research/quality.py::_check_range` does not flag `NaN` values as range violations (pandas
  comparison semantics: `NaN < lo` and `NaN > hi` are both `False`). Not contradicted by any
  docstring claim — `non_null` is the documented mechanism for catching nulls — so left as-is.
- `research/reproducibility.py::capture_run`'s `isinstance(param.value, int)` seed-detection
  check also accepts `bool` (since `bool` subclasses `int` in Python). No node in the codebase
  currently sets a boolean `seed`/`random_state` value, so this has no observed real-world
  impact; left unchanged as a very low-confidence, low-impact lead.
- `research/report.py::_render_html`'s XSS/escaping — thoroughly checked (`_escape` uses
  `html.escape`, applied to every title/description/byline/model-summary field); the "html"
  section kind is intentionally left unescaped per its documented contract (caller supplies
  already-rendered HTML), not a bug.

## Coverage & limitations
Covered every file in the commit's diff. Did not attempt to fuzz the regex patterns in
`clean/pii.py` exhaustively (only the false-positive/negative angle already documented as
acceptable), and did not install the real `presidio` package to test the `engine="presidio"`
branch beyond the existing monkeypatched test (which faithfully mirrors presidio's real
`analyze()`/`anonymize()` call signatures). The PDF fixture and `[docs]`-gated code path were
verified with a real, ad hoc `pypdf` install (not persisted to `pyproject.toml`).
