import { describe, expect, test } from "vitest";

import { validateMutation, validateSessionEvent } from "./validateMutation";

function validMutation(): unknown {
  return { base_version: 0 };
}

describe("validateMutation", () => {
  test("accepts a minimal valid mutation", () => {
    const result = validateMutation(validMutation());
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  test("rejects a mutation missing base_version", () => {
    const result = validateMutation({});
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});

describe("validateSessionEvent", () => {
  test("accepts a minimal valid event", () => {
    const result = validateSessionEvent({
      type: "proposal_added",
      session_id: "s1",
    });
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  test("rejects an event with an unknown type value", () => {
    const result = validateSessionEvent({
      type: "not_a_real_event",
      session_id: "s1",
    });
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  test("rejects an event missing session_id", () => {
    const result = validateSessionEvent({ type: "proposal_added" });
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});
