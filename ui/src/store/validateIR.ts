// PURE ajv-backed validation of the wire IR `Graph` against the committed JSON Schema
// (ui/src/generated/ir.schema.json), plus a first-class schema-version mismatch check.
//
// No React, no fetch, no store access -- this module only validates plain data so it can be
// unit-tested in isolation and reused by both the Import/Export UI (Task 06) and any future
// CLI/test tooling without coupling to the canvas runtime.

import Ajv2020 from "ajv/dist/2020";

import irSchema from "../generated/ir.schema.json";
import type { Graph } from "../generated/ir";

// Compile once at module load -- compilation is the expensive step, validation calls are cheap.
// strict:false because the Pydantic-emitted schema uses descriptive keywords (title, etc.) that
// ajv would otherwise warn/throw on; allErrors so callers see every problem, not just the first.
const ajv = new Ajv2020({ allErrors: true, strict: false });
const validateFn = ajv.compile(irSchema as object);

// The schema is the single source of truth for the supported version -- read it instead of
// hardcoding, so the canvas can't silently drift from the IR contract.
const schemaTyped = irSchema as unknown as {
  $defs: { Graph: { properties: { schema_version: { default: number } } } };
};
export const supportedSchemaVersion: number =
  schemaTyped.$defs.Graph.properties.schema_version.default;

export interface IRValidationResult {
  valid: boolean;
  errors: string[];
}

// Validate an IR graph against the published JSON Schema. errors are human-readable strings
// like "/nodes/node-1/type must be string".
export function validateIR(graph: unknown): IRValidationResult {
  const valid = validateFn(graph) as boolean;
  if (valid) return { valid: true, errors: [] };
  const errors = (validateFn.errors ?? []).map(
    (e) => `${e.instancePath || "(root)"} ${e.message ?? "is invalid"}`,
  );
  return { valid: false, errors };
}

// Returns a first-class mismatch message, or null when the graph's schema_version is absent
// (Pydantic default applies) or equals the supported version.
export function checkSchemaVersion(graph: Graph): string | null {
  const v = graph.schema_version;
  if (v === undefined || v === null || v === supportedSchemaVersion)
    return null;
  return (
    `This graph uses IR schema version ${v}, but this canvas supports version ` +
    `${supportedSchemaVersion}. Update Colony Mind (or migrate the graph) to open it.`
  );
}
