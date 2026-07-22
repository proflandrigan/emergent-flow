import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { IRToolbar } from "./IRToolbar";

beforeEach(() => {
  useGraphStore.getState().reset();
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
