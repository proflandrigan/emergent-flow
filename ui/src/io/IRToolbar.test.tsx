import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

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
