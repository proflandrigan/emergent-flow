import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { useFlowStore } from "./flowStore";
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
});
