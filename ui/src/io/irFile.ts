// Pure IR (de)serialization logic -- no React, no DOM. Lets `IRToolbar` stay a thin shell
// around Blob/file-input plumbing while this module stays unit-testable in isolation.

import type { Graph } from "../generated/ir";
import { checkSchemaVersion, validateIR } from "../store/validateIR";

export function serializeIR(graph: Graph): string {
  return JSON.stringify(graph, null, 2);
}

export interface ImportResult {
  graph?: Graph;
  error?: string;
}

// Parse + validate an IR JSON string. Order: JSON parse -> schema-version mismatch (first-class)
// -> ajv structural validation. Returns { graph } on success or { error } with a human message.
export function parseImport(text: string): ImportResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` };
  }
  const versionError = checkSchemaVersion(parsed as Graph);
  if (versionError) {
    return { error: versionError };
  }
  const { valid, errors } = validateIR(parsed);
  if (!valid) {
    return { error: `Not a valid IR graph: ${errors.slice(0, 3).join("; ")}` };
  }
  return { graph: parsed as Graph };
}
