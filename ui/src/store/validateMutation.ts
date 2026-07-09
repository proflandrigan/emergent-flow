// PURE ajv-backed validation of `GraphMutation` / `SessionEvent` against their committed JSON
// Schemas (ui/src/generated/mutation.schema.json, session_event.schema.json) -- the Epic 14
// Story 4 mirror of validateIR.ts for the collaboration-protocol shapes.
//
// No React, no fetch, no store access -- pure data validation, unit-testable in isolation.

import Ajv2020 from "ajv/dist/2020";

import mutationSchema from "../generated/mutation.schema.json";
import sessionEventSchema from "../generated/session_event.schema.json";
import type { IRValidationResult } from "./validateIR";

const ajv = new Ajv2020({ allErrors: true, strict: false });
const validateMutationFn = ajv.compile(mutationSchema as object);
const validateSessionEventFn = ajv.compile(sessionEventSchema as object);

function toResult(
  valid: boolean,
  errors: { instancePath: string; message?: string }[] | null | undefined,
): IRValidationResult {
  if (valid) return { valid: true, errors: [] };
  return {
    valid: false,
    errors: (errors ?? []).map(
      (e) => `${e.instancePath || "(root)"} ${e.message ?? "is invalid"}`,
    ),
  };
}

export function validateMutation(mutation: unknown): IRValidationResult {
  const valid = validateMutationFn(mutation) as boolean;
  return toResult(valid, validateMutationFn.errors);
}

export function validateSessionEvent(event: unknown): IRValidationResult {
  const valid = validateSessionEventFn(event) as boolean;
  return toResult(valid, validateSessionEventFn.errors);
}
