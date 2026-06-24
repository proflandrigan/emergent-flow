# UI ↔ Server Boundary — the import ban and the contract artifacts

- **Status:** Accepted
- **Date:** 2026-06-23
- **Deciders:** Colony Mind core team

## Context

[ADR 0013](./adr/0013-single-repo-bundled-ui-topology.md) collapsed the planned three-repo
split into one repository that ships the Python SDK and the bundled canvas (`ui/`) together
— the JupyterLab model. A single repo loses the *physical* wall that used to make a
frontend reach-in into Python impossible. ADR 0013 Decision 4 replaces that wall with a
discipline the repo must keep deliberately.

## The invariant (mechanically enforced)

**Nothing under `ui/` may `import`, `require`, or bundle the Python package.** The canvas
talks to the local server (`colonymind serve`) only over HTTP. This is the load-bearing
coupling rule from ADR 0013 Decision 3, and it is the one enforced by a check:

- `scripts/check_ui_boundary.py` scans every TypeScript/JavaScript source file under `ui/`
  (skipping `node_modules/`, `dist/`) and fails if any `import` / `export … from` /
  `require(...)` / dynamic `import(...)` statement names the package.
- It runs two ways: as the pytest gate `tests/test_ui_boundary.py`, and as a standalone
  CI step (`uv run python scripts/check_ui_boundary.py`) in `.github/workflows/ci.yml`.

A build-output *path string* (e.g. the Vite `outDir: "../colonymind/_static"`) is not an
import and is intentionally allowed — the UI writes its compiled assets there; it does not
import code from there.

## The contract artifacts (a stated convention)

Only three artifacts are intended to cross the `ui/ ↔ colonymind/` boundary, and they
cross as **data**, never as a code import:

1. the **IR JSON Schema** (Epic 1),
2. the **`compile_to_code` output string** (Epic 2), and
3. the **rules-as-data artifact** ([ADR 0012](./adr/0012-rules-as-portable-data.md)).

Per ADR 0013 Decision 4, this "only these three" rule is kept as a **convention** rather
than a brittle CI assertion that tries to enumerate exactly which artifacts move. The
mechanically-enforced half is the import ban above; the three-artifact rule is tightened
into an automated check only if it later proves trivially mechanizable. It pairs with
[ADR 0007](./adr/0007-open-core-licensing-boundary.md)'s still-deferred one-way-dependency
linter (the proprietary platform may depend on the open package; the open package must not
depend on platform code).
