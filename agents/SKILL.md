---
name: emergent-flow
description: >-
  Co-author Emergent Flow data/ML pipelines with a human on the live canvas. Use when asked to
  "build a pipeline", "analyse this CSV on the canvas", "review this flow", explain or walk
  through an Emergent Flow graph, run experiments on it, or propose graph changes over the
  local emergentflow serve HTTP API or its MCP tools.
---

# Emergent Flow

Emergent Flow is a visual data/ML platform: a graph IR edited on a live canvas, backed by a local
server. This skill lets you co-author a graph with a human on that canvas, proposing changes they
review, running the graph, and explaining results.

## Before you start

- Install the runtime: `pip install 'emergentflow[server,mcp]'`. This skill/plugin does NOT
  install the Python runtime.
- Make sure `emergentflow serve` is running (default `http://127.0.0.1:8765`). Check with
  `curl http://127.0.0.1:8765/healthz`.
- If MCP tools named like `add_node` or `create_session` are available, use them. Otherwise
  drive the HTTP API with curl.

## Read first

1. [Reply contract](./_reply-contract.md) - governs every reply to the human.
2. [Collaborator protocol](./emergent-flow-collaborator.md) - server, sessions, catalog,
   validate/compile, proposals, links, tours, open-question notes, reviews.

## Then load ONE persona, only if relevant

Don't load personas you don't need.

| Persona file | When to use |
| --- | --- |
| [data-modeller](./data-modeller.md) | Review `data.*` nodes: grain, join keys, schema |
| [data-scientist](./data-scientist.md) | Stats/modeling choices, evaluation |
| [researcher](./researcher.md) | Research questions, evidence, assumptions |
| [ml-engineer](./ml-engineer.md) | Training/serving, reproducibility, latency |
| [experimenter](./emergent-flow-experimenter.md) | One-change-at-a-time metric optimization with a ledger |

## Ground rules

- Propose changes as `GraphMutation`s the human reviews (or use the MCP mutation tools).
- Never edit flow files directly.
- Never put credentials in the graph; use env-var names only.
- Lead replies with the returned `view_url`.
- Put open questions on the canvas: an anchored `kind="open-question"` note or tour `unknowns`.
- Follow the [reply contract](./_reply-contract.md) for the shape of every reply.
