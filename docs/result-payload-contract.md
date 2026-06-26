# Result-Payload Contract — typed, sized renderable results

- **Status:** Accepted
- **Date:** 2026-06-23
- **Deciders:** Emergent Flow core team

## Context

`ef.execute` returns *inspectable* objects ([ADR 0002](./adr/0002-execute-the-ir-not-the-string.md)):
JSON-native values, Pydantic models, dataclasses, tidy DataFrames, and containers thereof. That
contract is a **superset** of JSON-native — a `pandas.DataFrame` or a `@dataclass`/Pydantic
result is inspectable yet not directly serializable, and a large DataFrame is not safe to ship
to a browser whole.

The local server ([ADR 0013](./adr/0013-single-repo-bundled-ui-topology.md), §A6) must hand the
frontend (roadmap Epic 8) a payload that is:

- **JSON-safe** — round-trips through `json.dumps`/`json.loads` with no Python-specific types.
- **Sized** — never balloons the response with a full large DataFrame.
- **Renderable without knowing Python types** — the frontend dispatches on a `kind` tag instead
  of inspecting the artifact's Python class.

This replaces the v0 best-effort `repr`/`to_dict` coercion shipped in Epic 4 Story 1. Story 3 is
the load-bearing contract for Epic 8's in-node rendering: stabilizing it now means the canvas can
build a renderer per `kind` without churn once Epic 8 starts.

## Where it lives

`emergentflow/server/payload.py::to_payload` is a single pure function, applied to every OUT-port
artifact inside `execute_graph` (`emergentflow/server/service.py`). It has no I/O and touches no
global state — `pandas`/`pydantic` are imported lazily inside the function so importing the
module stays light, and `torch` is never imported (unsupported objects, including
`torch.nn.Module`, are detected structurally by exclusion). Keeping it pure preserves the
ADR 0002 purity chain so the hosted tier can later wrap execution in sandboxing without
re-architecting this layer.

## Response shape

`POST /execute` returns:

```json
{
  "payload_version": 1,
  "results": { "<node_id>": { "<out_port_name>": { "kind": "...", "...": "..." } } },
  "statuses": { "<node_id>": { "status": "ok|error|skipped" } }
}
```

`results` is keyed `{node_id: {out_port_name: <payload>}}`. Note: a node whose status is `error`
or `skipped` is **absent** from `results` entirely — its outcome is reported only via `statuses`.

## The tagged union

Every OUT-port artifact becomes a dict with a `"kind"` discriminator. `to_payload` dispatches in
this order: scalar/text strings, then `pandas.DataFrame`, then dataclass/Pydantic records
(recursing into `to_payload` per field, so a nested DataFrame field still becomes `"table"`),
then generic JSON containers, falling back to `"unsupported"` for anything else.

### `scalar`

`None`, `bool`, `int`, `float`, or a `str` of at most `MAX_TEXT_CHARS` (16384) characters.
numpy scalars (`np.int64`, `np.bool_`, `np.float32`, …) are coerced to their native
Python equivalents and reported as `scalar`. Non-finite floats (`NaN`/`Infinity`)
become `null` so the payload is valid JSON for a browser's `JSON.parse`.

```json
{"kind": "scalar", "value": 42}
```

### `text`

A `str` longer than `MAX_TEXT_CHARS`, truncated to the first 16384 characters.

```json
{
  "kind": "text",
  "value": "<first 16384 chars>",
  "length": 50000,
  "truncated": true
}
```

### `table`

A `pandas.DataFrame`. The full frame is **never** serialized — `shape` reports the true size and
`head` carries only the first `MAX_HEAD_ROWS` (50) rows, JSON-safe (`NaN` → `null` via
`DataFrame.to_json`). `truncated` (and any "showing N of M" presentation) is derived by comparing
`len(head)` to `shape[0]`.

```json
{
  "kind": "table",
  "columns": ["a", "b"],
  "dtypes": ["int64", "float64"],
  "shape": [120, 2],
  "head": [{"a": 1, "b": 2.5}, {"a": 2, "b": null}],
  "truncated": true
}
```

### `record`

A dataclass or Pydantic `BaseModel` result. `fields` maps each field name to its own
`to_payload` output, so a `record` can contain a `table` (e.g. an `AnovaResult.summary`
DataFrame) or another nested `record`.

```json
{
  "kind": "record",
  "type": "AnovaResult",
  "fields": {
    "summary": {"kind": "table", "columns": ["..."], "dtypes": ["..."], "shape": [3, 4], "head": ["..."], "truncated": false},
    "p_value": {"kind": "scalar", "value": 0.013}
  }
}
```

### `json`

A `list`, `tuple`, or `dict` that round-trips through `json.dumps`/`json.loads` unchanged.

```json
{"kind": "json", "value": [1, 2, 3]}
```

### `unsupported`

Anything that doesn't match the above — e.g. a `torch.nn.Module` or any other live Python
object. `repr` is capped at `MAX_TEXT_CHARS`.

```json
{"kind": "unsupported", "type": "Linear", "repr": "Linear(in_features=4, out_features=1, bias=True)"}
```

## Sizing & truncation

Two caps, both defined in `emergentflow/server/payload.py`:

- `MAX_HEAD_ROWS = 50` — the number of DataFrame rows sampled into `table.head`.
- `MAX_TEXT_CHARS = 16384` — the cap applied to long strings (`text.value`) and to the `repr`
  fallback (`unsupported.repr`).

The governing rule: **never serialize a full large DataFrame into the response.** `to_payload`
always samples to `head` at the server and reports the true size via `shape`; the frontend
renders the sample and uses `truncated`/`shape` to show "N of M rows" without the server ever
holding (or transmitting) the complete frame in the JSON payload.

## Versioning

`PAYLOAD_CONTRACT_VERSION = 1` is emitted once as the top-level `payload_version` field on every
`/execute` response (`emergentflow/server/service.py::execute_graph`).

This version is **deliberately standalone** — it is NOT tied to the IR `schema_version`
(see [IR Serialization Format](./ir-serialization-format.md)). The IR schema version drives the
migration framework (`migrate_to_current`); coupling the payload contract to it would force
spurious IR schema bumps whenever only the wire *payload* shape changes, even though no graph
file needs migrating. The two contracts version independently and in parallel. Bump
`PAYLOAD_CONTRACT_VERSION` whenever a payload shape changes — a new `kind`, a renamed/added
field on an existing `kind`, or a changed truncation rule.

## Deferred (roadmap Epic 8)

Rich/large result types — e.g. HTML reports served as a lazily-fetched reference/blob — are
intentionally **not** built in Story 3. Extending the contract ahead of a concrete consumer would
mean building a blob-fetch path with no node that emits it and no renderer that needs it.

Today, with no such type defined:

- An HTML report string surfaces as `text` (truncated at `MAX_TEXT_CHARS` like any long string).
- A `torch.nn.Module` (or any other live object) surfaces as `unsupported`.

Extend this contract with a new `kind` only when a node actually emits a rich/large result *and*
Epic 8 is ready to render it.
