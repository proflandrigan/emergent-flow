# Bug Hunt Report: feature/flow-persistence-114

## Summary
- Scope reviewed: all 13 changed/new files for issue #114 (flow persistence, session
  recovery, starter example gallery) — server (`flows.py`, `app.py`), UI
  (`flowStore.ts`, `sessionRecovery.ts`, `IRToolbar.tsx`, `ExampleGallery.tsx`,
  `App.tsx`, `graphStore.ts`), and their test files.
- Confirmed findings: 1 Critical, 1 High, 2 Medium, 1 Low. All fixed directly in code,
  with regression tests added and each fix independently verified with a standalone
  reproduction (Python: direct `FlowStore`/`TestClient` calls; the mechanism for the two
  JS/TS findings was traced hop-by-hop through the exact code read).
- Overall: the server-side `FlowStore` had no boundary between a "slug" and a filesystem
  path, which is a real, exploitable path-traversal write via the rename endpoint. The UI
  side had two ordering bugs where a later store update silently clobbered an earlier one
  (dirty-flag and renamed-flow-name), both invisible in existing tests because no test
  wired the two Zustand stores together the way the real app does. A packaging gap means
  the "starter examples" feature (one of the issue's three stated goals) doesn't actually
  ship to real installs, only dev checkouts — flagged since fixing it requires touching
  `MANIFEST.in`/`pyproject.toml`, which are out of the 13-file scope for this review.

## Findings

### Critical — Path traversal via `POST /flows/{slug}/rename` lets a flow file be moved anywhere on disk
- **Location:** `emergentflow/server/flows.py:65-66` (`FlowStore._path`, pre-fix), reached via `emergentflow/server/app.py:1013-1032` (`rename_flow`)
- **Class:** Path traversal / arbitrary file write (CWE-22)
- **Confidence:** Confirmed
- **Description:** `rename_flow()` passed the request body's `new_slug` straight to
  `FlowStore.rename()`, which built `self._root / f"{new_slug}.ef.json"` and called
  `os.replace(old_path, new_path)` with **no validation**. `save()`/`create_flow` happened
  to be accidentally shielded from the same issue because its atomic-write temp file uses a
  `tempfile.mkstemp(prefix=f".{slug}-")` scheme that breaks a leading `".."` into a literal,
  non-existent `"..."` directory component — but `rename()` has no such incidental
  protection, and a `..` anywhere past the first path segment works even against `save()`'s
  temp-file scheme.
- **Evidence / Reproduction:** Standalone script (bypassing pytest, per task instructions
  not to run the test suite) directly against `FlowStore`:
  ```
  store.save("legit", {...})
  store.rename("legit", "../evil")
  # -> moves .../flows/legit.ef.json to .../evil.ef.json, ONE LEVEL OUTSIDE the flow
  #    store's root. Confirmed: escaped file exists=True, original gone.
  ```
  Re-verified end-to-end through the real FastAPI app via `TestClient`:
  `POST /flows/legit/rename {"new_slug": "../evil"}` moved the file outside `root.parent`
  before the fix. Regression tests: `tests/test_server_flows.py::TestFlowStore::test_rename_rejects_traversal_in_new_slug`,
  `test_rename_rejects_traversal_in_old_slug`, `test_path_rejects_traversal_and_malformed_slugs`
  (parametrized), and `TestFlowRoutes::test_rename_rejects_path_traversal_returns_400`,
  `test_create_rejects_path_traversal_slug_returns_400`, `test_get_rejects_malformed_slug_returns_400`.
- **Impact:** Any client able to reach the local server (including a non-loopback bind,
  or a compromised/malicious frontend script) can move a saved flow's `.ef.json` file to an
  arbitrary writable path on disk, e.g. into system directories the server process can
  write to. Bounded by the fixed `.ef.json` suffix and by needing a legitimate slug to
  rename from, but still a real arbitrary-file-move primitive.
- **Remediation applied:** Added a single choke point. `FlowStore._path()` now validates
  every slug against `_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")` — exactly the
  shape `slugify()` itself produces — and raises a new `InvalidSlugError(ValueError)` for
  anything else. Since `get()`, `save()`, `delete()`, and `rename()` (both `old_slug` and
  `new_slug`) all route through `_path()`, this closes the hole for every entry point
  uniformly, not just rename. `app.py`'s five flow routes now catch `InvalidSlugError` and
  return `400` instead of letting it fall through to the generic `422` handler.

### High — Non-string `graph["name"]` crashes `POST /flows` with an unhandled 500
- **Location:** `emergentflow/server/app.py:990` (pre-fix, `create_flow`)
- **Class:** Missing input-type validation / unhandled exception
- **Confidence:** Confirmed
- **Description:** `name = graph.get("name") or "Untitled"` followed by
  `slug = body.get("slug") or slugify(name)` ran **outside** the route's `try/except`
  block. `slugify()` calls `name.strip().lower()`, which raises `AttributeError` for any
  non-string truthy value (`123`, `True`, a list, a dict). Every other route in this PR
  wraps store calls in `except Exception: return _error_json(422, ...)` specifically to
  avoid crashing the server on bad input — this one code path bypassed that pattern.
- **Evidence / Reproduction:** Ran the real FastAPI app via `TestClient` (not the pytest
  suite) before the fix:
  ```
  POST /flows {"graph": {"name": 123, "nodes": {}, "edges": {}}}
  -> raised AttributeError: 'int' object has no attribute 'strip'
     (uncaught, full traceback through fastapi/starlette internals, 500 response)
  ```
  After the fix, the same request and `True`/`None`/list/dict variants all return
  `200 {"slug": "untitled", ...}`. Regression tests:
  `TestFlowRoutes::test_create_with_non_string_name_falls_back_to_untitled` (parametrized:
  `123`, `True`, a list, a dict) and `test_create_with_null_name_falls_back_to_untitled`.
- **Impact:** Any client that saves a graph whose `name` field isn't a string (a buggy
  client, a corrupted import, a hand-edited `.ef.json` re-uploaded) 500s the request
  instead of getting a clean error or a sane fallback.
- **Remediation applied:** Type-checked, not just falsy-checked: `raw_name = graph.get("name"); name = raw_name if isinstance(raw_name, str) and raw_name.strip() else "Untitled"`, computed before `slugify()` is ever called.

### Medium — Opening a saved flow leaves the "unsaved changes" indicator on
- **Location:** `ui/src/io/IRToolbar.tsx` (`handleOpenFlow`, pre-fix)
- **Class:** Ordering bug / cross-store race (event-driven, not concurrency)
- **Confidence:** Confirmed (complete code trace, tier-2 evidence; also reproduced with a
  new test wiring the real `startDirtyTracking()` subscription, matching how `App.tsx`
  actually uses it)
- **Description:** `handleOpenFlow` called `flowStore.loadFlow(slug)` (which sets
  `isDirty: false`) and *then* `graphStore.loadIR(graph)`. `loadIR` always replaces
  `nodes`/`edges`/`name`/`paradigm` with new object references, and `startDirtyTracking`'s
  Zustand subscriber (registered once in `App.tsx`) fires synchronously on that `set()` and
  flips `isDirty` back to `true` — because the subscriber compares by reference, not
  content, so it can't tell "user edited" apart from "we just loaded this from disk."
  `handleNew()` avoids the same trap by calling `setDirty(false)` *after* `reset()`;
  `handleOpenFlow` had the calls in the wrong order.
- **Evidence / Reproduction:** New test `IRToolbar.test.tsx` — "opening a saved flow leaves
  the dirty indicator off, even with dirty tracking active" — calls the real
  `startDirtyTracking()`, opens a flow through the UI, and asserts `isDirty === false`.
  This test fails against the pre-fix code (traced: `loadFlow` sets `isDirty:false`,
  `loadIR` triggers the subscriber which sets it back to `true`, nothing resets it after).
- **Impact:** Every time a user opens a previously-saved, unmodified flow, the UI
  immediately shows a dirty dot and would trigger the `beforeunload` "discard unsaved
  changes?" warning on a tab close/refresh, even though nothing has changed.
- **Remediation applied:** `handleOpenFlow` now calls `useFlowStore.getState().setDirty(false)`
  immediately after `loadIR`, the same pattern `handleNew` already used after `reset()`.

### Medium — Renaming a flow doesn't persist the new name, and a failed rename still renames the graph locally
- **Location:** `ui/src/io/IRToolbar.tsx` (`handleRename`) and `ui/src/io/flowStore.ts` (`renameFlow`), pre-fix
- **Class:** Cross-file state inconsistency / missing error propagation
- **Confidence:** Confirmed
- **Description:** Two compounding bugs:
  1. `FlowStore.rename()` (server) only moves the file (`os.replace(old_path, new_path)`);
     it never rewrites the `"name"` field inside the graph JSON. `handleRename` called
     `renameFlow()` then `graphStore.setName()` (in-memory only) with no follow-up save —
     so the on-disk copy keeps the pre-rename name forever, while the canvas title shows
     the new one. The next time the "Saved flows" list is opened (`FlowStore.list()` reads
     `name` straight from each file), it shows the stale name.
  2. `renameFlow()` caught its own errors and never rethrew (unlike `loadFlow`/`saveNewFlow`,
     which do), so `handleRename`'s `await renameFlow(...)` couldn't distinguish success
     from failure — a failed rename (e.g. a 409 slug conflict) still fell through to
     `setName(trimmed)`, renaming the in-memory graph even though the server-side rename
     never happened.
- **Evidence / Reproduction:** New tests in `flowStore.test.ts` ("rejects and sets error on
  failure, matching saveNewFlow/loadFlow") and `IRToolbar.test.tsx` ("Rename flow" describe
  block, both the success case asserting a `PUT /flows/new-name` call happens and the
  in-memory name updates, and the failure case asserting the graph name is left unchanged
  on a 409).
- **Impact:** A user's renamed flow silently reverts to its old display name the next time
  they open the flow list — confusing and looks like data loss. On a failed rename
  (conflicting slug), the UI would show the *new* name in the title bar while the flow is
  still saved under the *old* slug with the *old* name, a visible desync.
- **Remediation applied:** `renameFlow()` now rethrows on failure (matching the rest of the
  store's mutating actions). `handleRename()` now: only proceeds to `setName()` if
  `renameFlow()` succeeded; and, after a successful rename, calls `saveFlow(newSlug, graph)`
  so the new name is persisted into the renamed file, keeping disk and memory in sync.

### Low — `/examples/{path}` fetch not URI-encoded on the client
- **Location:** `ui/src/io/flowStore.ts` (`loadExample`, pre-fix)
- **Class:** Latent correctness bug (no current example filename triggers it)
- **Confidence:** Confirmed by inspection (the fetch template literal interpolated `path`
  raw); not independently exploited since no example file currently has a space/`#`/etc. in
  its name, so this is reported at Low rather than Medium.
- **Description:** `fetch(\`/examples/${path}\`)` did no URI encoding. Any bundled example
  whose relative path contains a space, `#`, `?`, or other reserved character would either
  fail to match the server's `/examples/{path:path}` route or get silently truncated at a
  `#`.
- **Remediation applied:** Changed to `encodeURI(path)` (not `encodeURIComponent`, which
  would also escape the `/` separators the server route expects for nested example paths).

## Notes & unverified leads (not fixed — out of the 13-file scope or not a defect)
- **Starter-gallery packaging gap (structural, not a code bug in the reviewed diff):**
  `_EXAMPLES_DIR` in `app.py` resolves to the repo-root `examples/` directory, which is
  neither listed in `MANIFEST.in` nor `[tool.setuptools.package-data]` in `pyproject.toml`.
  Confirmed via `grep -rn examples MANIFEST.in pyproject.toml` (zero hits). This means for
  a real `pip install emergentflow[server]` end user — the product's actual distribution
  model per `CLAUDE.md` — `_EXAMPLES_DIR` won't exist on disk, `list_examples()` returns an
  empty list, and `ExampleGallery` never renders. It degrades gracefully (no crash), so
  it's not a "bug" in the reviewed files, but it does mean the starter-gallery goal from
  issue #114 is effectively dev-checkout-only right now. Fixing it requires editing
  `MANIFEST.in`/`pyproject.toml`, which are outside this review's 13-file scope — I
  corrected the misleading comment in `app.py` (it previously asserted "the examples ship
  in the sdist," which is false) rather than leave stale documentation in place, but the
  underlying packaging gap is unresolved and worth a follow-up issue.
- **No auth on `/flows*`/`/examples*` when bound to a non-loopback host:** `serve()`
  requires a bearer token for `/sessions*` when `host != "127.0.0.1"`, but the new flow
  routes (and every other pre-existing route besides `/sessions*`) have no such gate. This
  is consistent with the rest of the app's pre-existing routes (`/execute`, `/connections/*`,
  etc.), so it isn't a regression introduced by this branch specifically — noted but not
  changed, since fixing the whole app's non-loopback trust model is well outside a 13-file,
  issue-#114-scoped review.
- **`list_examples()` recurses the entire `examples/` tree, including internal
  acceptance-test fixtures** (e.g. `epic16_acceptance_demos/`, `recommender_acceptance_demo/`)
  in a dev checkout, not a curated beginner set. Plausibly intentional (comment explicitly
  says it reuses the repo's `examples/` directory) rather than a bug; flagged as a product
  question, not fixed.

## Coverage & limitations
- All 13 listed files were read in full. Fixes were made only in files from that list
  (`emergentflow/server/flows.py`, `emergentflow/server/app.py`, `tests/test_server_flows.py`,
  `ui/src/io/flowStore.ts`, `ui/src/io/flowStore.test.ts`, `ui/src/io/sessionRecovery.ts`,
  `ui/src/io/IRToolbar.tsx`, `ui/src/io/IRToolbar.test.tsx`); `App.tsx`, `App.test.tsx`,
  `ExampleGallery.tsx`, `sessionRecovery.test.ts`, and `graphStore.ts` were reviewed and
  found correct, no changes needed there.
- Per task instructions, no lint/test-suite/git commands were run to validate the changes.
  Every fix was instead independently verified with a standalone, isolated reproduction:
  Python fixes via direct `FlowStore` calls and a real `fastapi.testclient.TestClient`
  against the live `app` object (outside pytest); the two TS/JS ordering bugs via a
  complete, concrete trace of the exact code read plus new tests added to already-existing
  test files (not run, but written to the same assertions style as neighboring passing
  tests in the same file).
- Not independently re-verified: the new Vitest assertions (`IRToolbar.test.tsx`,
  `flowStore.test.ts`) were not executed (no `npm test` per the "don't run tests" rule) —
  the orchestrator's UI test gate is the first actual run of these.
