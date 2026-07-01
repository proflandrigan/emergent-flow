import { describe, it, expect, beforeEach } from "vitest";

import { useExecutionStore } from "./executionStore";
import type { Payload } from "./execution";

describe("executionStore", () => {
  beforeEach(() => {
    useExecutionStore.getState().clear();
  });

  it("setRunning sets running: true, clears error and progress", () => {
    useExecutionStore.getState().setError("stale error");
    useExecutionStore.getState().setRunning();
    const state = useExecutionStore.getState();
    expect(state.running).toBe(true);
    expect(state.error).toBeNull();
    expect(state.progress).toBeNull();
  });

  it("setNodeStart sets progress", () => {
    useExecutionStore.getState().setNodeStart("Load CSV", 1, 3);
    expect(useExecutionStore.getState().progress).toEqual({
      current: 1,
      total: 3,
      label: "Load CSV",
    });
  });

  it("setNodeResult merges into results and sets status ok", () => {
    const payload: Payload = { kind: "scalar", value: 42 };
    useExecutionStore.getState().setNodeResult("node1", { output: payload });
    const state = useExecutionStore.getState();
    expect(state.results).toEqual({ node1: { output: payload } });
    expect(state.statuses).toEqual({ node1: { status: "ok" } });
  });

  it("setNodeResult preserves other nodes' existing results", () => {
    const p1: Payload = { kind: "scalar", value: 1 };
    const p2: Payload = { kind: "scalar", value: 2 };
    useExecutionStore.getState().setNodeResult("node1", { out: p1 });
    useExecutionStore.getState().setNodeResult("node2", { out: p2 });
    const state = useExecutionStore.getState();
    expect(state.results).toEqual({ node1: { out: p1 }, node2: { out: p2 } });
    expect(state.statuses).toEqual({
      node1: { status: "ok" },
      node2: { status: "ok" },
    });
  });

  it("setNodeCached merges into results and sets status cached", () => {
    const payload: Payload = { kind: "scalar", value: 42 };
    useExecutionStore.getState().setNodeCached("node1", { output: payload });
    const state = useExecutionStore.getState();
    expect(state.results).toEqual({ node1: { output: payload } });
    expect(state.statuses).toEqual({ node1: { status: "cached" } });
  });

  it("setNodeCached preserves other nodes' existing results", () => {
    const p1: Payload = { kind: "scalar", value: 1 };
    const p2: Payload = { kind: "scalar", value: 2 };
    useExecutionStore.getState().setNodeResult("node1", { out: p1 });
    useExecutionStore.getState().setNodeCached("node2", { out: p2 });
    const state = useExecutionStore.getState();
    expect(state.results).toEqual({ node1: { out: p1 }, node2: { out: p2 } });
    expect(state.statuses).toEqual({
      node1: { status: "ok" },
      node2: { status: "cached" },
    });
  });

  it("setNodeError sets that node's status to error without touching others", () => {
    useExecutionStore
      .getState()
      .setNodeResult("node1", { out: { kind: "scalar", value: 1 } });
    useExecutionStore.getState().setNodeError("node2", "boom");
    const state = useExecutionStore.getState();
    expect(state.statuses).toEqual({
      node1: { status: "ok" },
      node2: { status: "error", error: "boom" },
    });
  });

  it("setNodeSkipped sets that node's status to skipped without touching others", () => {
    useExecutionStore
      .getState()
      .setNodeResult("node1", { out: { kind: "scalar", value: 1 } });
    useExecutionStore.getState().setNodeSkipped("node2");
    const state = useExecutionStore.getState();
    expect(state.statuses).toEqual({
      node1: { status: "ok" },
      node2: { status: "skipped" },
    });
  });

  it("setRunComplete sets running: false and lastRunAt to a timestamp, clears progress", () => {
    useExecutionStore.getState().setRunning();
    useExecutionStore.getState().setNodeStart("L", 1, 1);
    useExecutionStore.getState().setRunComplete();
    const state = useExecutionStore.getState();
    expect(state.running).toBe(false);
    expect(state.lastRunAt).toEqual(expect.any(Number));
    expect(state.progress).toBeNull();
  });

  it("setError sets error and running: false but does NOT clear previously-set results", () => {
    useExecutionStore
      .getState()
      .setNodeResult("node1", { out: { kind: "scalar", value: 42 } });
    useExecutionStore.getState().setError("Connection failed");
    const state = useExecutionStore.getState();
    expect(state.error).toBe("Connection failed");
    expect(state.running).toBe(false);
    expect(state.results).toEqual({
      node1: { out: { kind: "scalar", value: 42 } },
    });
  });

  it("setError clears progress", () => {
    useExecutionStore.getState().setNodeStart("L", 1, 2);
    useExecutionStore.getState().setError("boom");
    expect(useExecutionStore.getState().progress).toBeNull();
  });

  it("clear resets to defaults", () => {
    useExecutionStore
      .getState()
      .setNodeResult("node1", { out: { kind: "scalar", value: 42 } });
    useExecutionStore.getState().setError("Some error");
    useExecutionStore.getState().clear();
    const state = useExecutionStore.getState();
    expect(state.running).toBe(false);
    expect(state.results).toEqual({});
    expect(state.statuses).toEqual({});
    expect(state.error).toBeNull();
    expect(state.progress).toBeNull();
  });

  it("clear resets lastRunAt to null", () => {
    useExecutionStore.getState().setRunComplete();
    useExecutionStore.getState().clear();
    expect(useExecutionStore.getState().lastRunAt).toBeNull();
  });

  it("setError does not clear lastRunAt", () => {
    useExecutionStore.getState().setRunComplete();
    const ts = useExecutionStore.getState().lastRunAt;
    useExecutionStore.getState().setError("boom");
    expect(useExecutionStore.getState().lastRunAt).toBe(ts);
  });
});
