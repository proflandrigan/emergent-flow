# Agent Quickstart — from an empty server to a run with metrics

The happy path for onboarding a new agent without re-deriving the collaboration protocol: start the
server (`emergentflow serve`), register the MCP bridge, `create_session` (and grab the `open_in_ui`
URL), read `/catalog` to learn the node types and their params, build the graph with the editing
tools, `/validate` + `compile_preview` as a preflight, `execute_session_tool` to get a persisted
`run_id`, then `get_results` / `get_metric` to read it back. This guide is the hands-on companion to
the reference docs — see [See also](#see-also) for the full HTTP route table and the canonical
worked walkthrough.

If you are an AI agent following this document, work top to bottom and confirm state with
`list_sessions()` / `get_graph(session_id)` after each mutating call.

## 0. Start the server

Start the local server (aliases `emergentflow serve` and `emergentflow lab`):

```bash
emergentflow serve
```

Check it is up:

```bash
curl http://127.0.0.1:8765/healthz
```

On the default loopback bind (`127.0.0.1`) the banner prints:

```
Emergent Flow - serving the local canvas at http://127.0.0.1:8765  (Ctrl-C to stop)
```

and the session routes are opened **without auth** (trusted-localhost).

**Non-loopback bind is different.** Binding to anything other than loopback (e.g. `--host 0.0.0.0`)
REQUIRES a bearer token. Pass it to `serve()` via `session_token=` or set the
`EMERGENTFLOW_SESSION_TOKEN` environment variable. The banner then prints a hint such as:

```
Session bearer token: <token>  (pass it to the agent as its Authorization: Bearer <token> header)
```

In that mode every `/sessions*` request (HTTP or MCP) must carry
`Authorization: Bearer <token>` from the agent.

## 1. Register the MCP bridge

The collaboration surface is exposed as MCP tools behind the optional `emergentflow[mcp]` extra
(`fastmcp`, stdio transport). To make the tools available to a client that supports `.mcp.json`-style
stdio registration (Claude Code, Gemini, Codex, OpenCode, …), register this entry:

```json
{
  "mcpServers": {
    "emergent-flow": {
      "command": "uv",
      "args": [
        "run", "--extra", "mcp",
        "python", "-c",
        "from emergentflow.collab.mcp import create_mcp_server; create_mcp_server().run()"
      ]
    }
  }
}
```

This requires `emergentflow[mcp]` installed (`uv sync --extra mcp` or
`pip install 'emergentflow[mcp]'`).

**Critical limitation — one surface at a time.** The MCP stdio server launched this way runs in a
**separate process** from `emergentflow serve`, and the session store (`get_default_store()` in
`emergentflow/collab/session.py`) is a process-wide singleton. A session created through the MCP
tools is therefore **NOT visible to the server's HTTP routes, and vice versa**. For a single-canvas
happy path, pick ONE surface and stay on it:

- **(a)** run everything through the MCP tools (this quickstart's default), or
- **(b)** drive the HTTP routes directly.

The `open_in_ui` link from `create_session` is for when the MCP bridge and the server share a session
store (currently not wired per ADR 0019 "one behavior, two doors"), so treat it as informational here.

## 2. Create a session

```python
create_session(graph: dict | None = None)
```

Call `create_session()` (optionally seeding an IR `graph` dict) and keep **both** fields it returns:

- `session_id` — the id for every subsequent tool call on this session.
- `open_in_ui` — a ready-to-open browser URL of the form
  `http://127.0.0.1:8765/?session=<id>` that a human can click to view/join the session on the
  canvas. (This `open_in_ui` field is what a create-session adds for exactly this purpose.)

Confirm what's live with `list_sessions()`.

## 3. Read the catalog

Before building anything, call `get_catalog_tool()` (same data as the HTTP `GET /catalog`) to find
valid node `type` strings and each one's `params` (names, defaults, required flags, type tokens) and
`ports`. Don't guess node types or param names — read the catalog. Nodes you add are
registry-validated, so a wrong `node_type` surfaces as an error.

## 4. Build the graph with tools

Add and wire nodes:

```python
add_node(session_id, node_type, *, label=None, params=None, position=None, ...)
```

- `add_node` accepts a dict for `params` and a dict for `position` (`{"x": ..., "y": ...}`) — pass
  params/position as dicts rather than flattened kwargs. It returns the new `node_id`. (Dict
  params/position support is the anti-friction fix on this happy path.)

```python
connect_ports(session_id, source_node_id, source_port_name, target_node_id, target_port_name, ...)
```

- `connect_ports` is **direction-aware**: it resolves the OUT port on the source and the IN port on
  the target. This means same-named in/out ports (e.g. `clean.explode_lists`'s `frame` appearing as
  both an IN and an OUT port) resolve correctly without ambiguity. It returns the new `edge_id`.

Adjust as needed:

```python
set_param(session_id, node_id, param_name, value, ...)
delete_node(session_id, node_id, ...)   # also removes incident edges
delete_edge(session_id, edge_id, ...)
```

Inspect as you go: `get_graph(session_id)` returns the full session document, and
`list_sessions()` lists every active session. After each edit, re-read `get_graph()` to confirm the
graph matches your intent.

## 5. Validate and compile (preflight)

Before executing, preflight the graph:

```python
validate_graph_tool(graph)         # or run_validity_checks_tool(graph)
```

- `validate_graph_tool(graph)` validates an IR graph and returns diagnostics (same as `POST /validate`).
- `run_validity_checks_tool(graph)` runs methodological validity rules (data leakage, train/test
  contamination, …) and returns findings with `rule_id`, `severity`, `message`, and implicated nodes.

Then eyeball the emitted Python before running it:

```python
compile_preview(graph)             # compile an IR dict, or
compile_session_tool(session_id)   # compile the session's CURRENT graph (respects open gates)
```

`compile_session_tool` returns `{"code": "..."}` on success, or `{"blocked_by_gates": [...]}` if any
gate is still OPEN.

## 6. Execute and read results

Execute the session's current graph:

```python
execute_session_tool(session_id, run_to=None, run_from=None, run_only=None)
```

- Returns `{"payload_version", "results", "statuses"}` (or `{"blocked_by_gates": [...]}`). Optional
  partial-execution scopes (`run_to` / `run_from` / `run_only`, mutually exclusive) are supported.
- **The returned `run_id` is persisted**: Task 8 saves each run to the `RunStore`, so the run
  survives and can be read back later.

Read the persisted run back:

```python
get_results(run_id)                        # digested summaries: scalars verbatim, tables as shape+head
get_node_outputs(run_id, node_ids)         # raw payloads per requested node
get_metric(run_id, node_id, metric_name)   # a single named scalar
compare_runs(run_id_a, run_id_b, node_id, metric_name)
```

`get_results` / `get_metric` / `compare_runs` / `get_node_outputs` all read the persisted run from
the `RunStore` — this is exactly why runs are saved.

**Optional gating on a human verdict.** If your flow should wait for a human to accept or reject a
proposal you posted before you proceed:

```python
await_verdict(session_id, proposal_id, timeout_seconds=30.0)
```

`await_verdict` long-polls for a `proposal_accepted` / `proposal_rejected` event on that proposal and
returns as soon as one lands (or the proposal already has a verdict). Two caveats: the wait is capped
at **600 seconds**, and a **negative `timeout_seconds` raises `ValueError`** — pass a
non-negative value. Under the MCP bridge the bridge client's read timeout is raised so a long poll can
complete. Propose and review first with `propose_mutation(session_id, mutation)` and
`post_review(session_id, review)`. Optional knowledge/attempt helpers exist too:
`save_knowledge_tool`, `list_knowledge_tool`, `get_knowledge_entry_tool`, `record_attempt_tool`.

## 7. Comparison / evaluation costing

`compare` runs one `evaluate` per recommender. Today `compare` defaults to **seven cheap metrics**,
and `diversity` is bounded by deterministic sampling, so comparing several recommenders on one canvas
is safe. A full 10-metric `evaluate` needs an explicit `metrics` list opt-in if you want the
quadratic-cost `diversity`. If the canvas fits multiple models, keep `compare` on its default metrics.

## Worked example (end to end)

Concrete walkthrough — teacher → article popularity-baseline recommender. Tool names and node
families are the real names; params/ports are illustrative but plausible, and mirror the catalog.

1. **Create a session.**

   ```python
   sess = create_session()
   session_id = sess["session_id"]          # keep this
   ui_url = sess["open_in_ui"]              # http://127.0.0.1:8765/?session=<id>
   ```

2. **Read the catalog** to find the node types and their params.

   ```python
   cat = get_catalog_tool()
   #   find a load node (data.load_parquet -> out "frame"), a data-prep node
   #   (recommend.prepare_interactions -> in "frame", out "interactions",
   #   params user_col/item_col), and the recommend family:
   #   recommend.fit (params={"algorithm": "popularity"}),
   #   recommend.compare (params={"k": 10}).
   ```

3. **Add nodes** — pass params and position as dicts:

   ```python
   load = add_node(session_id, "data.load_parquet", label="Teacher articles",
                   params={"path": "data/articles_events.parquet"},          # dict params
                   position={"x": 100, "y": 100})["node_id"]                 # dict position
   prep = add_node(session_id, "recommend.prepare_interactions",
                   label="Prepared interactions",
                   params={"user_col": "teacher_id", "item_col": "article_id",
                           "implicit": True})["node_id"]
   fit = add_node(session_id, "recommend.fit", label="Popularity baseline",
                  params={"algorithm": "popularity", "params": {}})["node_id"]
   cmp = add_node(session_id, "recommend.compare", label="Compare baselines",
                  params={"k": 10})["node_id"]
   ```

4. **Wire them** — `connect_ports` is direction-aware (source port is resolved OUT, target IN), so
   same-named ports resolve correctly:

   ```python
   connect_ports(session_id, load, "frame", prep, "frame")              # events   -> prepare
   connect_ports(session_id, prep, "interactions", fit, "interactions") # matrix   -> fit
   connect_ports(session_id, fit, "recommender", cmp, "recommenders")  # fitted   -> compare
   connect_ports(session_id, prep, "interactions", cmp, "test_interactions")  # test -> compare
   ```

5. **Inspect** with `get_graph(session_id)` to confirm the four nodes and four edges.

6. **Preflight.**

   ```python
   doc = get_graph(session_id)
   graph = doc["graph"]                               # the session's current IR graph dict
   validate_graph_tool(graph)                         # or run_validity_checks_tool(graph)
   compile_session_tool(session_id)                   # eyeball the emitted Python
   ```

7. **Execute and read metrics.**

   ```python
   exec_ = execute_session_tool(session_id)
   run_id = exec_["run_id"]                       # persisted to the RunStore
   get_results(run_id)
   ndcg = get_metric(run_id, cmp, "ndcg_at_k")
   hits = get_metric(run_id, cmp, "hit_rate")
   ```

   (Metric keys follow the recommend family: `precision_at_k`, `recall_at_k`, `ndcg_at_k`,
   `map_at_k`, `hit_rate`, `mrr_at_k`, … — confirm the exact set and column names against the
   `compare` result table via `get_results`.) Optionally `compare_runs(run_id_a, run_id_b, cmp,
   "ndcg_at_k")` after a second run, and gate on a human via
   `await_verdict(session_id, proposal_id, timeout_seconds=60)` before proceeding.

## See also

- [`docs/agent-integration.md`](./agent-integration.md) — the full HTTP route table plus the persona
  (data_modeller / data_scientist / researcher / ml_engineer) details.
- [`agents/emergent-flow-collaborator.md`](../agents/emergent-flow-collaborator.md) — the canonical
  worked walkthrough of the collaboration protocol.