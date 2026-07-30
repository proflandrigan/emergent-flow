import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { startDirtyTracking, stopDirtyTracking, useFlowStore } from "./flowStore";
import { IRToolbar } from "./IRToolbar";

beforeEach(() => {
  useGraphStore.getState().reset();
  useFlowStore.setState({
    currentSlug: null,
    isDirty: false,
    flows: [],
    examples: [],
    loading: false,
    error: null,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("importing a file with a mismatched schema version shows the error banner", async () => {
  render(<IRToolbar />);

  const file = new File(
    [
      JSON.stringify({
        paradigm: "functional",
        nodes: {},
        edges: {},
        schema_version: 999,
      }),
    ],
    "g.json",
    { type: "application/json" },
  );

  fireEvent.change(screen.getByTestId("ir-file"), {
    target: { files: [file] },
  });

  await waitFor(() =>
    expect(screen.getByTestId("ir-error")).toHaveTextContent("999"),
  );
});

describe("tidy layout button", () => {
  test("clicking Tidy layout repositions nodes", () => {
    const store = useGraphStore.getState();
    const aId = store.addNodeFromSpec(
      {
        type: "test",
        label: "A",
        version: 1,
        ports: [],
        params: [],
        paradigm: "functional",
        family: "test",
        description: "",
      },
      { x: 0, y: 0 },
    );
    const bId = store.addNodeFromSpec(
      {
        type: "test",
        label: "B",
        version: 1,
        ports: [],
        params: [],
        paradigm: "functional",
        family: "test",
        description: "",
      },
      { x: 0, y: 0 },
    );
    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("tidy-layout"));

    const nodesAfter = useGraphStore.getState().nodes;
    expect(nodesAfter[aId].position).not.toEqual(nodesAfter[bId].position);
  });
});

describe("File menu", () => {
  test("renders the File button", () => {
    render(<IRToolbar />);
    expect(screen.getByTestId("file-menu-toggle")).toHaveTextContent("File");
  });

  test("is closed until the File button is clicked", () => {
    render(<IRToolbar />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  test("clicking File shows New/Open/Save/Export/Import entries", () => {
    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));

    expect(screen.getByTestId("file-menu-new")).toBeInTheDocument();
    expect(screen.getByTestId("file-menu-open")).toBeInTheDocument();
    expect(screen.getByTestId("file-menu-save")).toBeInTheDocument();
    expect(screen.getByTestId("file-menu-save-as")).toBeInTheDocument();
    expect(screen.getByTestId("file-menu-rename")).toBeInTheDocument();
    expect(screen.getByTestId("file-menu-export")).toBeInTheDocument();
    expect(screen.getByTestId("file-menu-import")).toBeInTheDocument();
  });

  test("Rename is disabled when there is no current flow", () => {
    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    expect(screen.getByTestId("file-menu-rename")).toBeDisabled();
  });

  test("Rename is enabled once a flow has a currentSlug", () => {
    useFlowStore.setState({ currentSlug: "my-flow" });
    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    expect(screen.getByTestId("file-menu-rename")).not.toBeDisabled();
  });

  test("clicking Import JSON closes the menu", () => {
    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    fireEvent.click(screen.getByTestId("file-menu-import"));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("flow name", () => {
  test("shows 'Untitled' when the graph has no name", () => {
    render(<IRToolbar />);
    expect(screen.getByTestId("flow-name")).toHaveTextContent("Untitled");
  });

  test("displays the graph's name", () => {
    useGraphStore.getState().setName("My Flow");
    render(<IRToolbar />);
    expect(screen.getByTestId("flow-name")).toHaveTextContent("My Flow");
  });
});

describe("dirty indicator", () => {
  test("is absent when the flow store is clean", () => {
    useFlowStore.setState({ isDirty: false });
    render(<IRToolbar />);
    expect(screen.queryByTestId("dirty-indicator")).not.toBeInTheDocument();
  });

  test("appears when the flow store is dirty", () => {
    useFlowStore.setState({ isDirty: true });
    render(<IRToolbar />);
    expect(screen.getByTestId("dirty-indicator")).toBeInTheDocument();
  });

  // Regression test: opening a saved flow calls flowStore.loadFlow() (which sets isDirty:
  // false) and THEN graphStore.loadIR() (which replaces nodes/edges/name with new object
  // refs). If dirty tracking is active (as it always is in the real app, via
  // App.tsx's startDirtyTracking()), that second step alone flips isDirty back to true --
  // the freshly-opened, unmodified flow would incorrectly show as having unsaved changes.
  test("opening a saved flow leaves the dirty indicator off, even with dirty tracking active", async () => {
    startDirtyTracking();
    useFlowStore.setState({
      flows: [{ slug: "my-flow", name: "My Flow", updated_at: "2026-01-01T00:00:00Z" }],
    });
    const graph = { paradigm: "functional", nodes: {}, edges: {} };
    const flows = [{ slug: "my-flow", name: "My Flow", updated_at: "2026-01-01T00:00:00Z" }];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        const body = String(url).includes("/flows/") ? graph : { flows };
        return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
      }),
    );

    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    fireEvent.click(screen.getByTestId("file-menu-open"));
    fireEvent.click(screen.getByTestId("open-flow-my-flow"));

    await waitFor(() =>
      expect(useFlowStore.getState().currentSlug).toBe("my-flow"),
    );
    expect(useFlowStore.getState().isDirty).toBe(false);

    stopDirtyTracking();
    vi.unstubAllGlobals();
  });
});

describe("Rename flow", () => {
  // Regression test: FlowStore.rename() (server) only moves the file -- it never rewrites
  // the "name" field inside the graph JSON. Without an explicit save after a successful
  // rename, the saved-flows list (which reads `name` straight from disk) would keep showing
  // the pre-rename name forever, even though the canvas title and slug both moved on.
  test("on success, persists the new name under the new slug", async () => {
    useFlowStore.setState({ currentSlug: "old-slug" });
    useGraphStore.getState().setName("Old Name");
    vi.spyOn(window, "prompt").mockReturnValue("New Name");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ slug: "new-name" }),
      }) // POST /flows/old-slug/rename
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ flows: [] }) }) // renameFlow's fetchFlows refresh
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) }) // PUT /flows/new-name
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ flows: [] }) }); // saveFlow's fetchFlows refresh
    vi.stubGlobal("fetch", fetchMock);

    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    fireEvent.click(screen.getByTestId("file-menu-rename"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/flows/new-name",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    expect(useGraphStore.getState().name).toBe("New Name");
    expect(useFlowStore.getState().currentSlug).toBe("new-name");
  });

  // Regression test: a failed rename (e.g. a slug conflict) must not rename the in-memory
  // graph -- doing so would desync the displayed name from what's actually saved on disk
  // under the still-unchanged old slug.
  test("on failure, leaves the graph name unchanged", async () => {
    useFlowStore.setState({ currentSlug: "old-slug" });
    useGraphStore.getState().setName("Old Name");
    vi.spyOn(window, "prompt").mockReturnValue("New Name");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ error: "slug taken" }),
      }),
    );

    render(<IRToolbar />);
    fireEvent.click(screen.getByTestId("file-menu-toggle"));
    fireEvent.click(screen.getByTestId("file-menu-rename"));

    await waitFor(() => expect(useFlowStore.getState().error).toBe("slug taken"));
    expect(useGraphStore.getState().name).toBe("Old Name");
    expect(useFlowStore.getState().currentSlug).toBe("old-slug");
  });
});
