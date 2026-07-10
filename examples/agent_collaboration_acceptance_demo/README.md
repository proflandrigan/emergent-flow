# Agent Collaboration Acceptance Demo — seed graphs and transcripts

Epic 14 Story 12's two acceptance demos, in human-readable form.

## Files

| File | Description |
|------|-------------|
| `seed_graph_agent_builds.json` | The seed graph for the "agent builds, human accepts" demo: `n1` `data.load_csv` → `n2` `stats.describe`, wired by `e1`. |
| `seed_graph_human_builds.json` | The seed graph for the "human builds, agent reviews" demo: a single `n1` `data.load_csv` with a planted `encoding="latin-1"` flaw. |
| `transcript_agent_builds.md` | Human-readable `curl`-style transcript of the full call sequence — create session, discover, pre-flight, propose, accept, compile, execute. |
| `transcript_human_builds.md` | Human-readable `curl`-style transcript of the full call sequence — create flawed graph, post info/warning reviews, reply, apply fix, re-validate, compile, execute. |

## Source of truth

**These JSON and transcript files are a human-readable rendering for documentation
purposes.** The pytest files that CI actually runs and asserts against are:

- `tests/test_acceptance_demo_agent_builds.py`
- `tests/test_acceptance_demo_human_builds.py`

If these example files ever diverge from what the tests do, the pytest files are correct.

## Persona files

Both demos follow the protocol documented in
[`agents/emergent-flow-collaborator.md`](../../agents/emergent-flow-collaborator.md) (the main
collaboration protocol — find the server, join a session, read the graph + catalog, pre-flight,
propose, accept). The "human builds, agent reviews" demo additionally uses the
`data_modeller` persona from
[`agents/data-modeller.md`](../../agents/data-modeller.md) for its review findings and
attached fix.
