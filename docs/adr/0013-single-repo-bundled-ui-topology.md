# ADR 0013 — Single repo, single package: bundle the canvas UI with the SDK (JupyterLab model)

- **Status:** Accepted — supersedes the §A5 / decision-#11 topology stance of the
  [technical roadmap](../../planning_docs/technical_roadmap.md); amends [ADR 0007](0007-open-core-licensing-boundary.md) (UI placement only)
- **Date:** 2026-06-23
- **Deciders:** Colony Mind core team

## Context

The [technical roadmap](../../planning_docs/technical_roadmap.md) §A5 ("The frontend canvas
is a separate repo that consumes the IR — not a co-equal codebase") and its decision table
(#11) commit the product to **three separate repositories** — `colony-mind` (this SDK),
`colony-mind-canvas` (React/TS frontend), and `colony-mind-server` (FastAPI/Celery backend) —
coupled only through serialized artifacts. That decision was made to (a) keep the
IR-is-source-of-truth and execute-the-IR invariants clean ([ADR 0001](0001-graph-is-single-source-of-truth.md),
[ADR 0002](0002-execute-the-ir-not-the-string.md)), (b) separate the Python and TypeScript
toolchains, and (c) make the open-core boundary partly a *repo* boundary ([ADR 0007](0007-open-core-licensing-boundary.md)).

Two of those three goals do **not** actually require separate repositories — they require a
strict *coupling contract*. §A5 conflated the **coupling invariant** (the UI must never
`import colonymind`; the only things crossing the line are the IR JSON Schema, the
`compile_to_code` output string, and the Epic-5 rules-as-data artifact) with the **repo /
packaging topology** (how many repos, how the product ships). The invariant is load-bearing
and cheap to keep; the topology is negotiable and was optimized for a *team* with a clean
license wall, not for the current reality: a solo developer whose next milestone (Step 4 /
roadmap Epic 3) is the fastest path to a usable UI.

The desired end-user experience is the **JupyterLab model**: a single `pip install` delivers
both the Python data-science engine *and* a local web UI; a launch command boots a local
server that serves the canvas. JupyterLab is a TypeScript frontend plus a Python server that
talk only over a protocol (never a shared import), yet ship as one wheel with the compiled
frontend bundled as static assets. It is the existence proof that "single simple install" and
the §A5 coupling invariant are compatible. The intended monetization is the **dbt model**:
the local core (engine + single-user canvas) is open; a future hosted, gated "Cloud" product
is proprietary.

The forces:
- **Time-to-usable for a solo dev.** Cross-repo coordination, three CI pipelines, and three
  release cadences are pure overhead for one person. A monorepo lands cross-cutting features
  (the split Epics 4/8/10/14) in one PR.
- **Distribution.** `pip install colonymind` → `colonymind serve` is dramatically simpler to
  ship and explain than "install the SDK, then clone and `npm build` the canvas separately."
- **The coupling invariant must survive.** A separate repo *enforced* the no-reach-in rule by
  physical separation; a monorepo loses that wall and must replace it with discipline.
- **Open-core boundary (ADR 0007).** ADR 0007 places the visual UI in a separate *private*
  repo under "Platform Inventory." Bundling a local canvas into this Apache-2.0 package moves
  the open-core line: the single-user canvas becomes open source. This is consistent with the
  dbt model the project is targeting (open local core, gated cloud) but must be stated
  explicitly, because it changes what is open.

## Decision

We will collapse the planned three-repo split into **a single repository shipping a single
distributable Python package, `colonymind`, with the canvas UI bundled in — the JupyterLab
pattern — while preserving the §A5 coupling invariant in full.**

1. **One repo, one package.** This repository holds the SDK, the canvas UI, and (from Phase 2)
   a thin local server. We do **not** create `colony-mind-canvas` or `colony-mind-server` as
   separate repositories. Internal layout:

   ```
   colony-mind/
     colonymind/          # Python SDK + IR + codegen (unchanged)
       server/            # thin FastAPI app (Phase 2): serves the UI, calls cm.*
       _static/           # build artifact: compiled UI assets bundled into the wheel
     ui/                  # TypeScript/React canvas — own package.json, Vite, Vitest
     pyproject.toml       # build hook: `vite build ui/` → colonymind/_static/
   ```

2. **Bundled distribution.** The package build compiles `ui/` into `colonymind/_static/` and
   includes it in the wheel. `pip install colonymind` plus a launch command
   (`colonymind serve`, alias `cm lab`) boots a local server that serves the canvas. The SDK
   remains importable and fully functional headless (no UI/server required), preserving
   [ADR 0007](0007-open-core-licensing-boundary.md)'s portability guarantee.

3. **The coupling invariant is retained verbatim.** `ui/` **must not** import or bundle
   Python. The only artifacts crossing the `ui/ ↔ colonymind/` boundary are the three §A5
   contract artifacts: the IR JSON Schema (Epic 1), the `compile_to_code` output string
   (Epic 2), and the rules-as-data artifact ([ADR 0012](0012-rules-as-portable-data.md)). At
   runtime the UI talks to the local server over REST/WebSocket; the server is the only thing
   that calls `cm.*`. This keeps [ADR 0001](0001-graph-is-single-source-of-truth.md) /
   [ADR 0002](0002-execute-the-ir-not-the-string.md) intact: the IR is still the single source
   of truth and the frontend is still a pure consumer of the contract.

4. **Replace the repo wall with a CI wall.** Because the physical repo boundary no longer
   enforces the invariant, a CI check will: (a) assert `ui/` has no import or build-time
   dependency path into `colonymind` internals, and (b) assert that only the three named
   artifacts cross the boundary. A violation fails CI exactly as a forbidden cross-repo import
   would have been impossible before. The two toolchains stay separate by directory
   (`uv`/`ruff`/`mypy`/`pytest` for `colonymind/`; `npm`/Vite/Vitest for `ui/`), both run in
   one CI workflow.

5. **Phase-1 simplification (consequence we will exploit).** Because a thin local server can
   call the real `cm.validate` / `cm.compile_to_code` over localhost, the canvas does **not**
   need to reimplement validation or codegen in TypeScript for Phase 1. The client-side
   rules-as-data validator (§A5's reason for [ADR 0012](0012-rules-as-portable-data.md) being a
   Phase-1 frontend dependency) is downgraded to a **later latency optimization for the hosted
   product**, not a Step-4 requirement. ADR 0012's rules artifact remains the published
   contract and the authoritative-re-validator model is unchanged; only the *timing* of the
   client-side consumer moves.

6. **Open-core reconciliation (amends ADR 0007).** The open-core line moves: the **local,
   single-user canvas** is open source and ships in this Apache-2.0 package. Genuinely
   proprietary platform features — managed hosting, real-time multiplayer/collaboration,
   billing, execution orchestration, premium connector nodes — **remain in the separate
   private repository** per [ADR 0007](0007-open-core-licensing-boundary.md). This ADR amends
   ADR 0007 item 2 (the "this repo contains only the SDK" wording) and item 4's UI line (the
   canvas moves from Platform Inventory to the open core) while **preserving ADR 0007's
   licensing model and its one-way dependency rule**: the proprietary platform may depend on
   the open package; the open package must not depend on platform code. The future hosted
   "Cloud" product reuses these same open UI assets and local server, adding auth,
   multi-tenancy, and gating on top.

7. **Reversibility is preserved.** If a future need arises — a sharper license split, or a TS
   team whose npm release cadence diverges hard from the Python one — `ui/` can be extracted
   into its own repository mechanically, *precisely because* the coupling invariant (3) was
   kept. Extraction becomes a packaging change, not an architectural untangling. Revisit when
   (a) the gated Cloud product needs a firmer open/closed wall, or (b) release cadences
   diverge; until one of those bites, the monorepo stands.

## Consequences

**Positive:**
- One `pip install` ships the engine and the UI; a single launch command gives a usable local
  canvas. Far lower friction to adopt, demo, and explain than a multi-repo setup.
- A solo dev works in one repo with one CI and one version number; the cross-cutting epics
  (4, 8, 10, 14) land in single PRs instead of coordinated cross-repo changes.
- Step 4 shrinks: the canvas calls real Python validation/codegen over localhost rather than
  porting that logic to TypeScript (see Decision 5).
- The IR-as-source-of-truth and execute-the-IR invariants are untouched; the coupling contract
  is identical to §A5's, just enforced by CI rather than by repo separation.

**Negative / obligations:**
- The no-reach-in invariant is now a matter of discipline, not physics. We **must** land the
  CI boundary check (Decision 4) early, or the monorepo will accumulate exactly the
  "frontend reach-ins" §A5 warned about.
- Two toolchains live in one repo; contributors and CI must provision both Python and Node.
- The open-core line shifts: the single-user canvas becomes open source (Decision 6). This is
  intended (dbt model) but is a real change to ADR 0007 that must be ratified, not assumed.
- A mixed Python/TypeScript wheel build (bundling `ui/` → `_static/`) is more involved than a
  pure-Python build; the build hook and packaging need their own test.

**Deferred:**
- The concrete build-hook implementation and wheel-bundling test.
- **Update (2026-06-23):** a minimal local server now exists — `colonymind/server/` with a
  `colonymind serve` / `cm lab` entry point that calls `cm.compile_to_code` / `cm.execute` /
  `cm.validate` **in-process**. To keep the bundled install lean and zero-dependency for this
  v0 (the happy path of §A6), it uses the Python **stdlib** `http.server` rather than FastAPI;
  the FastAPI/WebSocket/streaming upgrade and the wheel-bundled `ui/` it will serve remain
  Phase 2. (Decision 1's "thin FastAPI app" names the eventual target, not the v0.)
- The CI boundary-check implementation (pairs with [ADR 0007](0007-open-core-licensing-boundary.md)'s
  still-deferred one-way-dependency linter).
- The concrete update to [ADR 0007](0007-open-core-licensing-boundary.md)'s SDK/Platform
  inventories (a future ADR may restate the open-core boundary in full); for now the amendment
  lives in Decision 6 above and is pointed to from ADR 0007's status line.
