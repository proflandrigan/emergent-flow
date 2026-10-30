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

  it("setRunComplete records run identity, defaulting finishedAt to a UTC ISO timestamp", () => {
    useExecutionStore.getState().setRunComplete({ runId: "r1", finishedAt: "2026-01-01T00:00:00+00:00" });
    expect(useExecutionStore.getState().runMeta).toEqual({
      runId: "r1",
      finishedAt: "2026-01-01T00:00:00+00:00",
    });
    useExecutionStore.getState().setRunComplete();
    const meta = useExecutionStore.getState().runMeta;
    expect(meta?.runId).toBeNull();
    expect(meta?.finishedAt).toMatch(/Z$/);
    useExecutionStore.getState().clear();
    expect(useExecutionStore.getState().runMeta).toBeNull();
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

describe("executionStore nodeRevisions", () => {
  beforeEach(() => {
    useExecutionStore.getState().clear();
  });

  it("records a revision per node and replaces it on a re-run", () => {
    const payload: Payload = { kind: "scalar", value: 1 };
    const s = useExecutionStore.getState();
    s.setNodeResult("n1", { out: payload }, "r1");
    s.setNodeCached("n2", { out: payload }, "r2");
    expect(useExecutionStore.getState().nodeRevisions).toEqual({ n1: "r1", n2: "r2" });
    useExecutionStore.getState().setNodeResult("n1", { out: payload }, "r3");
    expect(useExecutionStore.getState().nodeRevisions.n1).toBe("r3");
  });

  it("drops the previous revision when the event carries none, and clear() resets", () => {
    const payload: Payload = { kind: "scalar", value: 1 };
    useExecutionStore.getState().setNodeResult("n1", { out: payload }, "r1");
    useExecutionStore.getState().setNodeResult("n2", { out: payload }, "r2");
    // A new result with no stored revision must not sit next to the OLD revision.
    useExecutionStore.getState().setNodeResult("n1", { out: { kind: "scalar", value: 2 } });
    expect(useExecutionStore.getState().nodeRevisions).toEqual({ n2: "r2" });
    useExecutionStore.getState().setNodeCached("n2", { out: payload });
    expect(useExecutionStore.getState().nodeRevisions).toEqual({});
    useExecutionStore.getState().setNodeResult("n1", { out: payload }, "r1");
    useExecutionStore.getState().clear();
    expect(useExecutionStore.getState().nodeRevisions).toEqual({});
  });
});

describe("executionStore nodeRunMeta", () => {
  beforeEach(() => {
    useExecutionStore.getState().clear();
  });

  const p = (value: number): Payload => ({ kind: "scalar", value });

  it("stamps only the nodes produced in a run with that run's identity", () => {
    const s = useExecutionStore.getState();
    s.setRunning();
    s.setNodeResult("a", { out: p(1) }, "rev1");
    s.setNodeCached("b", { out: p(1) });
    s.setRunComplete({ runId: "run-1111", finishedAt: "2026-01-01T00:00:00+00:00" });
    s.setRunning();
    s.setNodeError("a", "boom");
    s.setRunComplete({ runId: "run-2222", finishedAt: "2026-01-02T00:00:00+00:00" });
    const st = useExecutionStore.getState();
    // a's held payload is still attributed to run 1, never the newer run 2.
    expect(st.nodeRunMeta.a).toEqual({ runId: "run-1111", finishedAt: "2026-01-01T00:00:00+00:00" });
    expect(st.nodeRunMeta.b.runId).toBe("run-1111");
    expect(st.runMeta?.runId).toBe("run-2222");
    expect(st.pendingRunNodes).toEqual([]);
  });

  it("records a null run id for a partial run (timestamp only)", () => {
    const s = useExecutionStore.getState();
    s.setRunning();
    s.setNodeResult("a", { out: p(1) });
    s.setRunComplete({ runId: null, finishedAt: "2026-01-03T00:00:00+00:00" });
    expect(useExecutionStore.getState().nodeRunMeta.a).toEqual({
      runId: null,
      finishedAt: "2026-01-03T00:00:00+00:00",
    });
  });

  it("stamps results received before a run_error with no run id, and clear() resets", () => {
    const s = useExecutionStore.getState();
    s.setRunning();
    s.setNodeResult("a", { out: p(1) });
    s.setError("lost");
    expect(useExecutionStore.getState().nodeRunMeta.a.runId).toBeNull();
    useExecutionStore.getState().clear();
    expect(useExecutionStore.getState().nodeRunMeta).toEqual({});
  });
});
