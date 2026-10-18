# ADR 0022 — Result cards: notebook-style results on the canvas

- **Status:** Accepted
- **Date:** 2026-10-18
- **Deciders:** Emergent Flow maintainers

## Context

Reading a node's output means clicking into it, which makes a canvas analysis much harder to
skim than a notebook. People (and agents) need findings — tables, charts, metrics, plus prose —
visible on the graph itself, with the underlying nodes still available for drill-down.

## Decision

We add `reports.result_card`, a real IR node (family `reports`) with one many-cardinality `any`
IN port (`results`) and params `title`, `blocks_json`, `width`. `blocks_json` is an ordered list of
`{"kind":"markdown","text"}` and `{"kind":"result","source":"<node_id>:<out_port>","caption"}` blocks.

- **ADR 0002:** `codegen` emits nothing and `execute` returns `{}`, so compiled output and
  execution are unchanged by the presence of a card; wiring only orders it after its sources.
- **Rendering:** the canvas renders the card live from the execution store using the existing
  `PayloadView`; prose is markdown. Sources that are unrun or failed show a placeholder.
- **Authoring:** edit mode on the card, a "Summarize" selection action that wires and seeds a
  card, and MCP tools `add_result_card` / `set_result_card` for agents (no new mutation type).
- **Export:** a client-side standalone HTML report of all cards (File → Export report).

## Consequences

Findings are skimmable without opening nodes, and agents can narrate results. Cards carry no
data flow, so they do not appear in compiled scripts. A server-side/notebook export and richer
chart blocks are deferred.
