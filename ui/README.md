# Colony Mind — canvas (ui/)

The bundled single-user canvas (ADR 0013). A Vite + TypeScript app that talks to the
local `colonymind serve` server over HTTP and is a **pure consumer** of its contract.

## Develop

```bash
cd ui
npm install
npm run dev        # Vite dev server
npm run build      # emits compiled assets into ../colonymind/_static/
npm run typecheck  # tsc --noEmit
npm test           # vitest run
npm run lint       # eslint .
npm run format     # prettier --check .
npm run gen:types  # regenerate TS types from ir.schema.json (schema itself from `uv run python scripts/export_ui_contracts.py`)
```

## Boundary rule (load-bearing)

This directory MUST NOT `import` or bundle the Python package. The only artifacts that
cross the `ui/ ↔ colonymind/` boundary are the IR JSON Schema, the `compile_to_code`
output string, and the rules-as-data artifact. A CI check enforces the import ban.
