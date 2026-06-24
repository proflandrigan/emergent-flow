# Epic 4 — Local Execution Server (bundled, in-process)

> **Repo ↔ roadmap numbering.** Epic files are numbered by **delivery order in this repo**;
> the [technical roadmap](../planning_docs/technical_roadmap.md) numbers epics **globally**.
> This file is repo **Epic 4** = the **happy-path sliver of roadmap Epic 6** (Backend Execution
> Runtime & Sandboxing). It was front-loaded *before* the frontend canvas (repo Epic 5 = roadmap
> Epic 3) on purpose — the SDK is proven and tested, so a thin server over it is the shortest
> path to a runnable app (see roadmap §A6 / §E and [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md)).
> The heavyweight remainder of roadmap Epic 6 — Celery, container sandboxing, distributed
> workers — is **(hosted)** and explicitly out of scope here. See [`epics/README.md`](./README.md).

> The bundled package's "Living Bridge": a thin **local** server that turns "Execute" into real
> Python by calling the SDK's pure `cm.*` entry points **in-process** on localhost — the
> JupyterLab/dbt-core trust model (you run your own code on your own machine). No Celery, no
> broker, no container sandbox, no auth, no multi-tenancy: those are the gated hosted product
> (§A6). This epic exists so `pip install colonymind` → `colonymind serve` is a real, demoable
> loop on top of the already-tested IR + codegen + executor.

**Phase:** 2 (Living Bridge) — happy-path sliver front-loaded into Phase 1.5.
**Lives in:** `colonymind/server/` (the SDK tree's local server; same package, headless-optional).
**Dependencies:** Epic 1 (IR + serialization), Epic 2 (`compile_to_code` / `execute`), Epic 3/roadmap-5 (`cm.validate`).
**Blocks:** repo Epic 5 (the canvas calls these endpoints instead of re-implementing codegen/validation in TS — [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 5); roadmap Epic 8 (result rendering consumes Story 3's payload contract).

---

## Definition of Done (epic-level)

- [x] `colonymind serve` (alias `cm lab`) boots a local server that calls `cm.compile_to_code` / `cm.execute` / `cm.validate` in-process and returns JSON.
- [x] The server is **zero-new-dependency** (stdlib `http.server`) and never crashes on a bad graph — failures come back as JSON.
- [x] The execution path stays **pure** (ADR 0002): the server only wraps the reference executor, so the hosted tier can later swap in sandboxing without re-architecting.
- [x] Execution granularity: "run all" + per-node status over the IR (Story 2); finer-grained "run this node" / "run to here" is deferred to land with the cache (Story 6 / roadmap Epic 7).
- [x] A **result-payload contract** — JSON-safe, sized/truncated renderable payloads — that roadmap Epic 8 (in-node rendering) consumes (Story 3).
- [x] `colonymind serve` serves the bundled canvas from `colonymind/_static/` once the `ui/` build hook exists (Story 4).
- [x] A CI **boundary check** asserts `ui/` never imports `colonymind`; the "only the three contract artifacts cross the line" rule is documented as a convention rather than a brittle CI assertion ([ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 4) (Story 5).
- [x] Celery / container sandboxing / distributed & streaming execution are explicitly **not** built here — deferred to the hosted product (§A6).

---

## Story 1 — In-process v0 server, CLI entry point & tests ✅ (done)

> The shortest path to "an app, not a library." Delivered ahead of the canvas because every
> function it wraps is already tested.

- [x] `colonymind/server/service.py`: pure-ish wrappers `compile_graph` / `validate_graph` / `execute_graph` taking an IR dict and returning JSON-native dicts (DataFrame results coerced JSON-safe).
- [x] `colonymind/server/app.py`: stdlib `http.server` exposing `POST /compile`, `/execute`, `/validate`, `GET /healthz`, and a throwaway paste-IR demo page at `GET /`.
- [x] Graceful failure: any `cm.*` error is returned as a `422` JSON `{"error": ...}`, never a server crash.
- [x] `colonymind/cli.py` + `[project.scripts] colonymind = "colonymind.cli:main"`: `serve` / `lab` subcommands with `--host` / `--port`.
- [x] `tests/test_server.py`: service-level + HTTP round-trip tests, including a real in-process execute of the bundled sample CSV and the graceful-error path. Green under the four CI gates.

---

## Story 2 — Execute the graph (run all + per-node status) ✅ (done)

> The minimum that makes the canvas runnable: execute the whole graph and report per-node
> status so the UI can colour nodes. Finer-grained granularity is deferred (Story 6).

- [x] A "run all" request that executes the whole IR and returns results per OUT port.
- [x] Return per-node status (ok / error / skipped) so the canvas can colour nodes (consumed by repo Epic 5 Story 8).
- [x] Keep it pure and in-process; no caching yet (that's roadmap Epic 7 — note the seam).
- [x] Tests over a multi-node graph asserting results + per-node status come back.

---

## Story 3 — Result-payload contract (the Epic 8 boundary)

> The frontend can only render what the server hands it. Define the *minimal* renderable
> payload now — scalars and tables — so in-node visualization (roadmap Epic 8) builds against a
> stable contract. Rich/large result types (HTML reports, big blobs) are defined when Epic 8
> needs them, not pre-built here.

- [x] Define a JSON-safe, **sized** payload per OUT port: small scalars/JSON inline; tabular results as `{columns, dtypes, shape, head: [...]}` with a truncation flag ("showing N of M").
- [x] Replace the v0 `repr`/`to_dict` best-effort coercion (Story 1) with this typed contract.
- [x] Never serialize a full large DataFrame into the response — sample/truncate to `head` at the server.
- [x] Version the payload shape with its own standalone version (decoupled from the IR schema version, to avoid spurious migrations); document it in `docs/`.
- [x] Tests: a wide/long DataFrame truncates to the declared `head`.
- [ ] **Deferred to roadmap Epic 8:** rich/large result types (e.g. HTML reports as a lazily-fetched reference/blob) — extend this contract only when a node actually emits them and Epic 8 renders them, to avoid building a blob-fetch path with no consumer.

---

## Story 4 — Serve the bundled canvas ✅ (done)

> The JupyterLab payoff: one launch command opens the real UI, not a paste box.

- [x] Serve static assets from `colonymind/_static/` (the built `ui/` tree) when present; fall back to the v0 demo page when absent.
- [x] `colonymind serve` prints the URL and (optionally) opens a browser tab (`--no-browser` opts out).
- [x] Coordinate with the `ui/` build hook (`vite build ui/` → `colonymind/_static/`, [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 1) and the wheel-bundling test. Implemented as an in-tree PEP 517 backend (`build_backend.py`) that runs `vite build` best-effort on a real wheel build and skips cleanly when Node is absent (the editable/dev path never invokes Node). **Follow-up:** wire a Node setup step into `release.yml` so published wheels actually bundle the canvas — until then `uv build` on the Node-less release runner ships a pure-Python wheel.
- [x] Tests: with a stub `_static/index.html`, `GET /` serves it; without, the demo page still works.

---

## Story 5 — CI boundary check (replace the repo wall) ✅ (done)

> [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 4: the monorepo loses
> the physical repo wall, so a CI check must enforce the coupling invariant instead.

- [x] A check that fails CI if anything under `ui/` imports/bundles `colonymind` or reaches into Python internals (`scripts/check_ui_boundary.py` + `tests/test_ui_boundary.py`). **This import ban is the mechanically-enforced invariant.**
- [x] Document the contract-artifact boundary (only the IR JSON Schema, `compile_to_code` output, and rules-as-data cross `ui/ ↔ colonymind/`) as a stated convention in [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 4 / `docs/` (`docs/ui-server-boundary.md`) — rather than a brittle "exactly these three artifacts" CI assertion. Tighten into an enforced check only if it later proves trivially mechanizable.
- [x] Wire the import ban into `.github/workflows/ci.yml` alongside the existing Python gates (pairs with ADR 0007's still-deferred one-way-dependency linter).

---

## Story 6 — Incremental execution granularity ✅ (done — built ahead of the cache)

> Originally deferred out of Story 2 to land with the cache (roadmap Epic 7). Built now at
> the maintainer's direction (branch `epic4-story4to6`): the request shapes are stateless and
> reuse the Epic 2 traversal + wiring, so they stand alone. The on-disk happy-path cache
> remains roadmap Epic 7 — until it lands, re-running still recomputes, and "run this node"
> relies on the caller supplying inputs (rich DataFrame inputs round-trip faithfully only
> once the cache exists). See the `run_to` / `run_node` envelopes on `/execute` / `/execute_node`.

- [x] "Run to here": a request shape selecting a target node (or set) that executes only the subgraph up to and including it, reusing the Epic 2 traversal + wiring (`run_to` envelope on `/execute`; ancestor-closed subgraph).
- [x] "Run this node": execute a single node given already-available upstream inputs (`/execute_node`, `run_node` + `inputs`).
- [x] Tests over a fan-out graph asserting only the requested subgraph executes.
- [ ] ~~Sequence alongside the on-disk happy-path cache (roadmap Epic 7), not before it.~~ Intentionally not honored — granularity shipped ahead of the cache; the cache remains roadmap Epic 7.

---

## Notes / Risks (carry into planning)

- **Keep the executor pure.** The whole point of the in-process v0 is that ADR 0002's purity lets the hosted tier wrap it in sandboxing later. Do not let server convenience leak I/O or global state into `cm.execute`.
- **Resist scope creep into the hosted tier.** Celery, containers, WebSocket streaming, auth, multi-tenancy are §A6 **(hosted)** — every one of them added here is over-architecting the local app. Ship granularity + result payloads + serving the UI first.
- **The cache (roadmap Epic 7) is separate but adjacent.** The v0 re-runs everything; that's fine until edits feel slow. Story 2 ships run-all and leaves the seam; finer-grained granularity (Story 6) and the on-disk happy-path cache land together as their own epic.
- **Story 3 is the load-bearing contract** for the frontend's most uncertain work (Epic 8). Stabilize it before the canvas renders results, or the UI churns.

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
