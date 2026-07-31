import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./runsClient", () => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  getRunGraph: vi.fn(),
  deleteRun: vi.fn(),
}));

import { useRunsStore } from "./runsStore";
import { listRuns, getRun, deleteRun } from "./runsClient";

beforeEach(() => {
  useRunsStore.getState().clearSelection();
  vi.clearAllMocks();
});

describe("fetchRuns", () => {
  it("populates the runs list", async () => {
    const mockRuns = [{ run_id: "r1", timestamp: 100, duration_ms: 50, node_count: 3, tag: null, graph_name: null }];
    (listRuns as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockRuns);
    await useRunsStore.getState().fetchRuns();
    expect(useRunsStore.getState().runs).toEqual(mockRuns);
    expect(useRunsStore.getState().loading).toBe(false);
  });

  it("sets error on failure", async () => {
    (listRuns as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("Network error"));
    await useRunsStore.getState().fetchRuns();
    expect(useRunsStore.getState().error).toBe("Network error");
    expect(useRunsStore.getState().loading).toBe(false);
  });
});

describe("selectRun", () => {
  it("fetches and sets the run detail", async () => {
    const mockDetail = { run_id: "r1", statuses: {}, reproducibility: { seeds: {}, content_hashes: {}, dependency_versions: {} }, sdk_version: "0.3.3" };
    (getRun as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockDetail);
    await useRunsStore.getState().selectRun("r1");
    expect(useRunsStore.getState().selectedRunId).toBe("r1");
    expect(useRunsStore.getState().selectedRunDetail).toEqual(mockDetail);
  });

  it("clears selection when null", async () => {
    useRunsStore.getState().selectRun(null);
    expect(useRunsStore.getState().selectedRunId).toBeNull();
  });
});

describe("deleteRun", () => {
  it("removes the run and refreshes the list", async () => {
    (deleteRun as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    (listRuns as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    await useRunsStore.getState().deleteRun("r1");
    expect(deleteRun).toHaveBeenCalledWith("r1");
  });
});