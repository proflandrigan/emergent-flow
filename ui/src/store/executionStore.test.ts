import { describe, it, expect, beforeEach } from "vitest";

import { useExecutionStore } from "./executionStore";
import { EXPECTED_PAYLOAD_VERSION } from "./execution";
import type { ExecuteResponse, Payload } from "./execution";

describe("executionStore", () => {
  beforeEach(() => {
    useExecutionStore.getState().clear();
  });

  it("setResult populates results + statuses and sets running: false", () => {
    const scalarPayload: Payload = { kind: "scalar", value: 42 };
    const response: ExecuteResponse = {
      payload_version: 2,
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
      payload_version: 2,
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
      payload_version: 2,
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

  it("setResult sets lastRunAt to a timestamp", () => {
    expect(useExecutionStore.getState().lastRunAt).toBeNull();

    const response: ExecuteResponse = {
      payload_version: 2,
      results: { node1: { output: { kind: "scalar", value: 42 } } },
      statuses: { node1: { status: "ok" } },
    };

    useExecutionStore.getState().setResult(response);

    expect(useExecutionStore.getState().lastRunAt).toEqual(expect.any(Number));
  });

  it("clear resets lastRunAt to null", () => {
    const response: ExecuteResponse = {
      payload_version: 2,
      results: { node1: { output: { kind: "scalar", value: 42 } } },
      statuses: { node1: { status: "ok" } },
    };

    useExecutionStore.getState().setResult(response);
    useExecutionStore.getState().clear();

    expect(useExecutionStore.getState().lastRunAt).toBeNull();
  });

  it("setResult rejects incompatible payload_version and sets error without touching results", () => {
    const staleResponse: ExecuteResponse = {
      payload_version: EXPECTED_PAYLOAD_VERSION - 1,
      results: { node1: { output: { kind: "scalar", value: 99 } } },
      statuses: { node1: { status: "ok" } },
    };
    useExecutionStore.getState().setResult(staleResponse);
    const state = useExecutionStore.getState();
    expect(state.error).toMatch(/incompatible/);
    expect(state.results).toEqual({});
    expect(state.running).toBe(false);
  });

  it("setError does not clear lastRunAt", () => {
    const response: ExecuteResponse = {
      payload_version: 2,
      results: { node1: { output: { kind: "scalar", value: 42 } } },
      statuses: { node1: { status: "ok" } },
    };

    useExecutionStore.getState().setResult(response);
    const ts = useExecutionStore.getState().lastRunAt;

    useExecutionStore.getState().setError("boom");

    expect(useExecutionStore.getState().lastRunAt).toBe(ts);
  });
});
