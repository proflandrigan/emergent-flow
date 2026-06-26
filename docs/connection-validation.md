# Connection Validation: Rules as a Portable Artifact

The Emergent Flow Python SDK defines type compatibility rules for its visual
data/ML platform. These rules are shipped to the separate frontend canvas
(`emergent-flow-canvas`, which never does `import emergentflow`) as data, not code.
This page documents how that data is structured and used. It is the Epic 3
Story 7 deliverable, built on the type model of [ADR 0011](./adr/0011-type-model-and-compatibility.md)
and the rules-as-data decision of [ADR 0012](./adr/0012-rules-as-portable-data.md).

## The exported artifacts

Two artifacts are committed in `schema/`:

- `schema/rules.json`: contains the type compatibility rules.
- `schema/diagnostics.schema.json`: defines the JSON Schema of validation
  diagnostics returned by `ef.validate(graph)`.

The `rules.json` artifact has this exact structure:

```json
{
  "semantics": {
    "exact": true,
    "subtype": true,
    "unknown": "warn",
    "wildcard": "any"
  },
  "subtypes": [],
  "top": "any",
  "types": [
    "AnovaResult",
    "ClassifierResult",
    "DataFrame",
    "HTML",
    "Tensor",
    "any"
  ],
  "version": 1
}
```

Fields:
- `types`: all registered type tokens (sorted).
- `top`: the wildcard token `"any"`.
- `subtypes`: declared `[subtype, supertype]` edges (currently none).
- `semantics`: flags the frontend uses to reimplement the tiny check.
- `version`: the IR schema version (`CURRENT_SCHEMA_VERSION`, currently `1`).

## The compatibility rule

The compatibility check is three-valued — `compatible` / `incompatible` /
`unknown` — and follows this precedence:

1. **Wildcard**: if either side is `"any"` → compatible.
2. **Unknown**: if either token is not registered → unknown (warn, do not block).
3. **Exact**: tokens are equal → compatible.
4. **Subtype**: source is a registered transitive subtype of target → compatible.
5. **Otherwise** → incompatible.

This logic is implemented in the SDK and mirrored by the canvas for fast UX. Note
this is *structural* type compatibility only: `Tensor` → `Tensor` is compatible
here; per-dimension shape checking is a future epic, not part of these rules.

## Authority model

The frontend uses `rules.json` for instant, offline feedback during graph
construction — red edges as you drag, no server round-trip. However, the SDK is
the authoritative re-validator. Server-side validation (Epic 6) runs
`ef.validate` and its verdict is final. If the two disagree (e.g., a stale
artifact), the SDK wins. The canvas provides fast UX, not correctness of record.

## Versioning and drift

The artifact's `version` aligns with the IR schema version
(`CURRENT_SCHEMA_VERSION`). A version bump signals the canvas to refresh its rules
artifact, tying into the Epic 14 migration story. A CI test fails if the committed
artifacts are out of sync with changes to the type catalog or the `Diagnostics`
model, preventing silent drift.

## Regenerating the artifacts

To regenerate the committed artifacts:

```bash
python -m emergentflow.types.rules_artifact schema/rules.json
python -m emergentflow.codegen.diagnostics_schema schema/diagnostics.schema.json
```

In-process Python APIs:
- `ef.build_rules_artifact()` returns the `rules.json` dict.
- `ef.diagnostics_json_schema()` returns the Diagnostics JSON Schema dict.
