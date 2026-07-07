# ADR 0018 — Data-source connectors are a second injected effectful-client seam; connection references stay secret-free

- **Status:** Accepted
- **Date:** 2026-07-07
- **Deciders:** SDK maintainers (proflandrigan)

## Context

Repo Epic 13 (Data Connectors, Warehouses & SQL — the bundled/local slice of roadmap Epic 9)
introduces nodes that **query external data warehouses** (BigQuery, Redshift, Postgres, and the
in-process DuckDB): a node takes a SQL string or a structured query spec and a named connection,
and returns a `DataFrame`. This is the same shape of problem [ADR 0017](./0017-llm-nodes-injected-effectful-client.md)
already faced for LLM nodes — **non-deterministic, credentialed, metered network I/O** — colliding
with the two invariants the whole product rests on:

- **ADR 0002** requires that running the code from `compile_to_code(ir)` produce artifacts
  **equivalent** to `execute(ir)`, and that **both functions stay pure** — no I/O, no global state —
  so the executor can later be sandboxed. This equivalence is a CI gate.
- **ADR 0001** keeps the graph IR the single source of truth, and the IR must stay serializable and
  shareable — it is exported to Git and sent to teammates, so it **cannot embed a live DB connection
  or a literal credential** (a host, token, password, or DSN).

ADR 0017 solved exactly this for LLM calls by quarantining the effect behind an injected `LLMClient`
seam, with a `ReplayClient` keeping the equivalence gate value-exact and offline, and a secrets rule
that carries an env-var *name* (`api_key_env`) in the IR, never the key. That decision was written
for one effect type and threaded a single `client` parameter through `execute` and the compiled
module's entry point. Epic 13 forces two questions ADR 0017 did not have to answer:

1. **A second effect type now exists.** `requires_client: bool` currently *implies the LLM client*,
   and `execute(graph, *, client=...)` / the compiled `main(client=...)` thread exactly one client.
   A warehouse node needs a *different* injected client. Do we add a second boolean and a second
   positional parameter, or generalize the seam so it scales to the further effects the roadmap
   anticipates (object storage, the Epic 11 vector store)?
2. **Warehouse credentials are richer than one env-var name** — a host, port, database, project,
   dataset, region, and an auth *method* (a password, a service-account key, ADC, a keyring handle).
   Where does that live, given the IR must stay secret-free *and* the same warehouse is referenced by
   many nodes across many graphs?

The forces to reconcile are ADR 0017's four (purity, equivalence-without-the-network, real usage,
secrets) **plus** extensibility (this is now the second of N effect types) and a cost/safety dimension
LLM calls had in miniature but warehouses have acutely (a wrong query scans terabytes and bills real
money). The rejected framing — again — is a new "connector" node tier exempt from the equivalence
gate. That forks the node contract and punches a permanent hole in ADR 0002. We keep the invariant
intact, exactly as ADR 0017 did.

## Decision

**We will treat data-source connectors as a second instance of ADR 0017's injected-client seam, resolve
all injected clients through one extensible bundle, and keep every connection reference in the IR
secret-free.**

1. **A `WarehouseClient` protocol is the single data-source seam, mirroring `LLMClient`.** Its job is
   `run(request: QueryRequest) -> QueryResult`, plus read-only introspection (`list_relations`,
   `describe_relation`) and a `dry_run(request) -> CostEstimate`. A `QueryRequest` is a fully-built,
   deterministic, JSON-native, hashable structure (compiled SQL, dialect, connection **name**, bound
   params, row/byte limits, `read_only`, `dry_run`); building it from node inputs — including compiling
   a structured query spec to dialect SQL via `sqlglot` — is **pure**. Running it is the **only**
   effect, and it lives entirely inside the client. `QueryResult` is the inspectable dataclass (a tidy
   `DataFrame` plus JSON-native metadata: `row_count`, column schema, `bytes_scanned`, `cost_usd`,
   `dialect`, `truncated`, `elapsed_ms`); a live connection, cursor, or driver object is never returned.

2. **Injected clients are resolved through one extensible bundle, not a growing list of parameters.**
   `execute(graph, *, clients=Clients(...))` and the compiled module's `main(clients=...)` take a
   single `Clients` bundle exposing named seams (`clients.llm`, `clients.warehouse`, extensible to
   future effects). A node declares the capabilities it needs (a capability set superseding the bare
   `requires_client` boolean); the executor resolves each seam from the bundle and hands it to the
   node. Nodes never construct a client, import a driver, read `os.environ`, or open a socket — they
   call a `ctx`-resolved `clients.warehouse.run(...)`, exactly as LLM nodes call `client.complete(...)`.

3. **Back-compatibility is a hard requirement.** The existing `execute(graph, *, client=...)` keyword
   and the `requires_client` boolean keep meaning *the LLM client*, via a shim that maps them onto
   `Clients(llm=...)`. Every Epic 9 LLM node, its tests, and its golden output are untouched, and a
   graph with **no** warehouse nodes compiles and executes byte-identically to before. The bundle is
   additive: graphs gain access to a new seam without any existing behavior changing.

4. **Connection references in the IR are secret-free — ADR 0017's `api_key_env` rule, generalized.**
   The IR carries a **connection-profile name** (e.g. `connection="warehouse_prod"`) and nothing else
   about the connection. A `ConnectionProfile` — dialect, connection coordinates, auth *method* +
   credential *references* (env-var names, a keyring handle, or ADC), and default limits — is a named,
   serializable, **secret-free** descriptor kept in a **local** store outside the IR (a
   `connections.toml` and/or the OS keyring). Only the effectful `WarehouseClient` resolves a profile
   name to live credentials, from the environment or keyring, at `run()` time. No host, token,
   password, or DSN is ever serialized into the IR or the emitted code, logged, or committed.

5. **`ReplayWarehouseClient` keeps the equivalence gate value-exact and offline.** A pure
   `ReplayWarehouseClient` replays a recorded `QueryResult` keyed by `QueryRequest.content_hash()` and
   raises on a miss (the `emergentflow.llm.replay` shape). It is the default in tests and the ADR-0002
   harness: handed the **same** replay client, `execute` and the compiled module build identical
   requests, replay identical results, and produce value-equivalent artifacts — so the gate is
   unchanged, just parametrized by a second client. **DuckDB** (an in-process, credential-free adapter)
   is a real feature *and* the offline backend that records fixtures, so the whole matrix runs in CI
   without a cloud account. CI never touches BigQuery/Redshift.

6. **`execute` and `compile_to_code` remain pure functions of `(ir, clients)`.** Given pure clients
   (the replay clients), both are pure and deterministic. The impurity is exactly and only the clients
   you choose to inject — an explicit, sandboxable boundary, one per effect type, not a property
   smeared through the node graph.

7. **Cost and safety are properties of the effectful client, not the pure core.** Read-only-by-default
   (a `sqlglot`-parsed statement allow-list), row/byte caps, `dry_run`-before-spend cost estimates, and
   query timeouts are configured on the profile / node params and **enforced inside the client /
   adapter**. They never appear inline in `execute` or `compile_to_code`; a violation is a typed error.

## Consequences

**Easier / positive**

- ADR 0002 survives intact: one equivalence gate, value-exact, now parametrized by two injected
  clients through a single bundle. No second-class node tier, no forked contract, no weakened invariant.
- `execute` / `compile_to_code` stay pure and therefore stay sandboxable.
- The IR stays serializable, shareable, and secret-free: a `.ef.json` graph that queries production can
  be committed or sent to a teammate without leaking a single credential (only a profile *name*).
- The seam is now demonstrably extensible: the Epic 11 vector store and a future object-store connector
  are new entries on the `Clients` bundle, not another positional parameter and another `requires_*`
  boolean.
- Warehouse breadth (BigQuery/Redshift/Postgres/DuckDB) rides per-dialect adapters behind the one
  `WarehouseClient`; swapping a real adapter for a replay, caching, or budget-guard client is a
  one-line injection, not a node change — the ADR-0017 provider-agnosticism benefit, generalized.
- Cost/bytes/latency tracking rides on `QueryResult` and is inspectable by construction under
  `@public_op`.

**Harder / negative**

- `execute` and the compiled entry point move from a single `client` to a `clients` bundle — a
  signature change that must thread through the server (Epic 7) and the CLI. Mitigated by the
  back-compat shim (clause 3): the old `client=` keyword and `requires_client` boolean keep working, so
  the change is additive and no existing LLM path breaks.
- Recorded `QueryResult` fixtures are now test artifacts to maintain; a SQL/spec change invalidates a
  fixture and requires a re-record step (a documented `--record` mode, recording against DuckDB where
  possible, mitigates this — the ADR-0017 fixture-maintenance cost, generalized).
- A local connection-profile store is a new stateful surface outside the IR that the SDK, server, and
  UI must agree on. This is deliberate — it is where the secrets the IR must not hold actually live —
  but it is a new thing to document, back up, and (in the hosted product) replace with a managed store.
- The equivalence gate proves `execute ≡ compiled` **under a fixed client**; it proves nothing about
  live-warehouse output (non-deterministic by nature, and data changes under you). That is correct and
  intended — value-equivalence is a statement about the pure core, not about the warehouse.

**Deferred**

- **Pushdown.** v1 *pulls* the query result into the engine; pushing downstream graph computation back
  down into SQL is a later performance play, not part of this seam.
- **Writes / DML / DDL.** The seam is read/query + introspect. Table materialization (dbt-style
  `CREATE TABLE AS`) and a full dbt integration are out of scope; the read-only default is the safe
  boundary until a writes decision is made deliberately.
- **A managed, per-workspace secret store and premium/managed connectors** are the hosted product
  (roadmap §A6). This ADR settles the *local* profile store + the seam; the hosted store is a
  drop-in `ConnectionProfile` resolver behind the same boundary.
- **Result caching across runs** (warehouse queries are slow and metered) is a caching `WarehouseClient`
  decorator, layered later without touching nodes — the ADR-0017 caching-decorator deferral, generalized.
