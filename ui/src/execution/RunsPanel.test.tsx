import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RunsPanel } from "./RunsPanel";

import { useRunsStore } from "./runsStore";
import { useGraphStore } from "../store/graphStore";
import { useFlowStore } from "../io/flowStore";

vi.mock("./runsStore", () => ({
  useRunsStore: vi.fn(),
}));

vi.mock("../store/graphStore", () => ({
  useGraphStore: vi.fn(),
}));

vi.mock("../io/flowStore", () => ({
  useFlowStore: vi.fn(),
}));

vi.mock("./runsClient", () => ({
  getRunGraph: vi.fn(),
}));

function createMockStore(overrides: Record<string, unknown> = {}) {
  const defaultStore = {
    runs: [],
    selectedRunId: null,
    selectedRunDetail: null,
    compareRunId: null,
    compareRunDetail: null,
    loading: false,
    error: null,
    fetchRuns: vi.fn(),
    selectRun: vi.fn(),
    selectCompareRun: vi.fn(),
    clearSelection: vi.fn(),
    deleteRun: vi.fn(),
    clearError: vi.fn(),
    ...overrides,
  };
  (useRunsStore as unknown as Mock).mockImplementation(
    (selector: ((state: Record<string, unknown>) => unknown) | undefined) => {
      return selector ? selector(defaultStore) : defaultStore;
    },
  );
  return defaultStore;
}

beforeEach(() => {
  vi.clearAllMocks();
  createMockStore();
  (useGraphStore as unknown as Mock).mockReturnValue({ getState: () => ({ loadIR: vi.fn() }) });
  (useFlowStore as unknown as Mock).mockReturnValue({ getState: () => ({ isDirty: false, setDirty: vi.fn() }) });
});

describe("RunsPanel", () => {
  it("renders empty state", () => {
    render(<RunsPanel onClose={vi.fn()} />);
    expect(screen.getByTestId("runs-panel")).toBeDefined();
    expect(screen.getByTestId("runs-panel-empty")).toBeDefined();
  });

  it("renders runs list", () => {
    createMockStore({
      runs: [
        { run_id: "r1", timestamp: 100, duration_ms: 50, node_count: 3, tag: "baseline", graph_name: "Test" },
      ],
    });
    render(<RunsPanel onClose={vi.fn()} />);
    expect(screen.getByTestId("run-entry-r1")).toBeDefined();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn();
    render(<RunsPanel onClose={onClose} />);
    fireEvent.click(screen.getByTestId("runs-panel-close"));
    expect(onClose).toHaveBeenCalled();
  });
});
