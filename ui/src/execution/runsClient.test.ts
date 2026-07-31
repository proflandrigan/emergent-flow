import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

import { listRuns, getRun, getRunGraph, deleteRun } from "./runsClient";

beforeEach(() => {
  mockFetch.mockReset();
});

describe("listRuns", () => {
  it("returns the runs list from a successful response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ runs: [{ run_id: "r1", timestamp: 100, duration_ms: 50, node_count: 3, tag: null, graph_name: null }] }),
    });
    const runs = await listRuns();
    expect(runs).toHaveLength(1);
    expect(runs[0].run_id).toBe("r1");
  });

  it("throws on error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ error: "Server error" }),
    });
    await expect(listRuns()).rejects.toThrow("Server error");
  });
});

describe("getRun", () => {
  it("returns the run detail", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ run_id: "r1", statuses: {}, reproducibility: { seeds: {}, content_hashes: {}, dependency_versions: {} }, sdk_version: "0.3.3" }),
    });
    const detail = await getRun("r1");
    expect(detail.run_id).toBe("r1");
  });
});

describe("getRunGraph", () => {
  it("returns the graph dict", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ name: "Test", nodes: {} }),
    });
    const graph = await getRunGraph("r1");
    expect(graph.name).toBe("Test");
  });
});

describe("deleteRun", () => {
  it("sends a DELETE request", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });
    await deleteRun("r1");
    expect(mockFetch).toHaveBeenCalledWith("/runs/r1", expect.objectContaining({ method: "DELETE" }));
  });
});