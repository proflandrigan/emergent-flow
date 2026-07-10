# Agent Collaboration — pairing an AI agent with `emergentflow serve`

A human and an AI agent co-author one graph through a shared server-side session — the agent
never edits files, it calls HTTP routes (or MCP tools) to read, propose, and review. The
architectural reasoning behind the session model, trust boundary, and HTTP-first/MCP-second
surface is in [ADR 0019](./adr/0019-graph-sessions-and-agent-collaboration.md).

## HTTP surface

[`agents/emergent-flow-collaborator.md`](../agents/emergent-flow-collaborator.md) is the
canonical worked walkthrough: find the server → sessions → catalog → validate/compile
preflight → submit a proposal → await the verdict via SSE → post reviews with anchored
findings. Read it before wiring up an agent.

The full route surface the agent talks to:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/sessions` | List active sessions |
| `POST` | `/sessions` | Create a new session (optionally seeded with a graph) |
| `GET` | `/sessions/{id}` | Read a session's graph, version, proposals, reviews |
| `DELETE` | `/sessions/{id}` | Remove a session |
| `PUT` | `/sessions/{id}/graph` | Replace the session graph wholesale (with expected version) |
| `POST` | `/sessions/{id}/proposals` | Submit a `GraphMutation` proposal (validated on arrival) |
| `POST` | `/sessions/{id}/proposals/{pid}/accept` | Accept a pending proposal and merge its mutation |
| `POST` | `/sessions/{id}/proposals/{pid}/reject` | Reject a pending proposal (no version bump) |
| `GET` | `/sessions/{id}/events` | SSE stream of proposal/review events |
| `POST` | `/sessions/{id}/reviews` | Post a `ReviewThread` with anchored findings |
| `GET` | `/sessions/{id}/reviews` | List all review threads on a session |
| `POST` | `/sessions/{id}/reviews/{rid}/comments` | Append a reply to a review thread |
| `GET` | `/catalog` | Return the versioned node catalog (types, params, ports) |
| `POST` | `/validate` | Validate a full graph IR and return diagnostics |
| `POST` | `/compile` | Compile a graph IR to Python code (preview) |
| `GET` | `/personas` | List registered `AgentPersona` entries |

## MCP config for Claude Code

The same collaboration surface is also available as MCP tools behind the optional
`emergentflow[mcp]` extra. `create_mcp_server()` in
[`emergentflow/collab/mcp.py`](../emergentflow/collab/mcp.py) builds a `fastmcp.FastMCP`
instance exposing 8 tools (`get_graph`, `list_sessions`, `get_catalog_tool`,
`validate_graph_tool`, `compile_preview`, `propose_mutation`, `post_review`,
`await_verdict`) that delegate to the same functions the HTTP routes call.

To expose these tools to Claude Code, add an entry to your Claude Code MCP config
(`~/.claude/settings.json` or project `.claude/settings.json`):

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

`FastMCP.run()` defaults to `stdio` transport, which is what Claude Code's MCP client
expects. This requires `emergentflow[mcp]` to be installed (`uv sync --extra mcp` or
`pip install 'emergentflow[mcp]'`).

**Important limitation:** The MCP server launched this way runs in a **separate process**
from `emergentflow serve`. The session store (`get_default_store()` in
`emergentflow/collab/session.py`) is a process-wide singleton — each process gets its own
empty `SessionStore`. Sessions you create via `emergentflow serve`'s HTTP routes will NOT be
visible to the MCP tools, and vice versa. If you need both surfaces to share sessions, they
must run inside the same process — e.g. by calling `create_mcp_server()` inside the server's
startup lifecycle (not currently wired; Epic 14 ships the MCP wrapper as detached by design,
per ADR 0019's "one behavior, two doors" principle). For now, choose one surface — HTTP or
MCP — per process.

## Persona-file authoring

A persona is pure metadata that tells the canvas and agents what a collaborator is for. The
`AgentPersona` model
([`emergentflow/collab/personas.py`](../emergentflow/collab/personas.py)):

| Field | Type | Purpose |
|-------|------|---------|
| `slug` | `str` | Unique registry key (e.g. `"data_modeller"`) |
| `label` | `str` | Human-facing short name |
| `description` | `str` | One-line summary |
| `node_families` | `list[str]` | Node families this persona reviews (empty = all) |
| `system_prompt` | `str \| None` | Prompt for Mode B (server-side consult, Story 8) |
| `source_path` | `str \| None` | Relative path to a persona markdown file for Mode A agents |

### Registration

Built-in personas are registered in
[`emergentflow/collab/persona_defs.py`](../emergentflow/collab/persona_defs.py) through
`register_builtin_personas()`. The pattern is:

```python
MY_PERSONA = AgentPersona(
    slug="my_persona",
    label="My Persona",
    description="Reviews X nodes for Y.",
    node_families=["some_family"],
    source_path="agents/my-persona.md",
)

def register_builtin_personas() -> None:
    for persona in (MY_PERSONA,):
        with contextlib.suppress(ValueError):
            register_persona(persona)
```

The registry is a flat dict keyed by `slug` — no inheritance, no discovery, just
`register_persona()` / `get_persona()` / `list_personas()`. `register_builtin_personas()` is
called inside `serve()` before Uvicorn starts; third parties can call `register_persona()`
at any point before a request hits `GET /personas`.

### Persona markdown convention

The two shipped personas — [`agents/data-modeller.md`](../agents/data-modeller.md) and
[`agents/researcher.md`](../agents/researcher.md) — share a common structure:

1. A short intro stating who the persona is (e.g. "You are a data modelling reviewer,
   focused on `data.*` nodes").
2. A pointer to [`agents/emergent-flow-collaborator.md`](../agents/emergent-flow-collaborator.md)
   for the full HTTP protocol, with a note like "this file only adds the domain-specific
   review checklist below."
3. A **What to check** section (`##`-headed) listing the domain concerns as a bullet list
   with concrete node-type references.
4. A **Worked example** (`##`-headed) with a real `curl` command posting a review with one
   finding and an optional fix.

New persona files should follow this same shape. The checklist items reference real node
types and param names that exist in the catalog — if you're reviewing a family the catalog
doesn't cover yet, file an issue rather than documenting hypothetical nodes.

## Shards pairing recipe

This repository does not own Shards or ship it, and does not maintain a link to its
documentation here — consult Shards' own project for installation and configuration. Once
Shards is installed:

1. **Point Shards at a persona file** — configure Shards to use one of the `agents/*.md`
   files in this repository as its agent persona (e.g.
   `agents/emergent-flow-collaborator.md` for the generic collaborator, or
   `agents/data-modeller.md`/`agents/researcher.md` for domain-flavoured reviewers). How
   Shards discovers its persona file is Shards' concern — this repo provides the markdown,
   not the wiring.
2. **Start `emergentflow serve`** — boot the local server:
   ```bash
   emergentflow serve
   # Emergent Flow - serving the local canvas at http://127.0.0.1:8765
   ```
3. **Confirm connectivity** — from the agent's environment (or any terminal), verify the
   server is reachable:
   ```bash
   curl -s http://127.0.0.1:8765/healthz
   # {"status":"ok"}
   ```
4. **The agent now has the full surface** — it can create/list sessions, read the graph and
   catalog, validate/compile preflights, submit proposals, await verdicts over SSE, and post
   reviews with anchored findings, exactly as documented in
   [`agents/emergent-flow-collaborator.md`](../agents/emergent-flow-collaborator.md).

## Trust boundary reminder

Session routes are open by default when the server binds to `127.0.0.1` (the Jupyter-style
trusted-localhost model). Binding to any non-loopback host requires a bearer token — either
passed as `session_token=` to `serve()` or set as `EMERGENTFLOW_SESSION_TOKEN` in the
environment — and the server will refuse to start without one. See the "Trust boundary"
section of [ADR 0019](./adr/0019-graph-sessions-and-agent-collaboration.md) for the full
reasoning.
