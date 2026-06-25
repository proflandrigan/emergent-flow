import { describe, it, expect, beforeEach } from "vitest";

import { useExecutionStore } from "./executionStore";
import type { ExecuteResponse, Payload } from "./execution";

describe("executionStore", () => {
  beforeEach(() => {
    useExecutionStore.getState().clear();
  });

  it("setResult populates results + statuses and sets running: false", () => {
    const scalarPayload: Payload = { kind: "scalar", value: 42 };
    const response: ExecuteResponse = {
      payload_version: 1,
      results: {
        node1: { output: scalarPayload },
      },
      statuses: {
        node1: { status: "ok" },
      },
    };

    useExecutionStore.getState().setResult(response);
    const state = useExecutionStore.getState();

    expect(state.results).toEqual(response.results);
    expect(state.statuses).toEqual(response.statuses);
    expect(state.running).toBe(false);
    expect(state.error).toBeNull();
  });

  it("setError sets error and running: false but does NOT clear previously-set results", () => {
    // First, set a result
    const scalarPayload: Payload = { kind: "scalar", value: 42 };
    const response: ExecuteResponse = {
      payload_version: 1,
      results: {
        node1: { output: scalarPayload },
      },
      statuses: {
        node1: { status: "ok" },
      },
    };

    useExecutionStore.getState().setResult(response);

    // Then set an error
    useExecutionStore.getState().setError("Connection failed");
    const state = useExecutionStore.getState();

    expect(state.error).toBe("Connection failed");
    expect(state.running).toBe(false);
    // Results should still be present
    expect(state.results).toEqual(response.results);
    expect(state.statuses).toEqual(response.statuses);
  });

  it("clear resets to defaults", () => {
    // Set some data
    const scalarPayload: Payload = { kind: "scalar", value: 42 };
    const response: ExecuteResponse = {
      payload_version: 1,
      results: {
        node1: { output: scalarPayload },
      },
      statuses: {
        node1: { status: "ok" },
      },
    };

    useExecutionStore.getState().setResult(response);
    useExecutionStore.getState().setError("Some error");

    // Clear
    useExecutionStore.getState().clear();
    const state = useExecutionStore.getState();

    expect(state.running).toBe(false);
    expect(state.results).toEqual({});
    expect(state.statuses).toEqual({});
    expect(state.error).toBeNull();
  });
});
