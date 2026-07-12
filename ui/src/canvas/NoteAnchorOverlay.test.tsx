import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { Canvas } from "./Canvas";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const loadCsv = requireCatalogNode("data.load_csv");
const markdownNote = requireCatalogNode("notes.markdown");

beforeEach(() => {
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
});

describe("NoteAnchorOverlay", () => {
  test("no notes -> renders the overlay svg with zero leader lines", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    render(<Canvas />);

    expect(screen.getByTestId("note-anchor-overlay")).toBeInTheDocument();
    expect(screen.queryAllByTestId("note-anchor-line")).toHaveLength(0);
  });

  test("note anchored to a real node renders one leader line", () => {
    const targetId = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 100 });
    const noteId = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 300, y: 300 });
    useGraphStore.getState().setParam(noteId, "anchor_id", targetId);
    useGraphStore.getState().setParam(noteId, "content", "explaining this node");

    render(<Canvas />);

    expect(screen.getAllByTestId("note-anchor-line")).toHaveLength(1);
  });

  test("unanchored note renders zero leader lines", () => {
    useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 0, y: 0 });

    render(<Canvas />);

    expect(screen.queryAllByTestId("note-anchor-line")).toHaveLength(0);
  });

  test("note with a stale anchor_id renders zero leader lines (no error)", () => {
    const noteId = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 0, y: 0 });
    useGraphStore.getState().setParam(noteId, "anchor_id", "does-not-exist");

    render(<Canvas />);

    expect(screen.queryAllByTestId("note-anchor-line")).toHaveLength(0);
  });

  test("two notes anchored to the same target render two leader lines", () => {
    const targetId = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 100 });
    const noteA = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 300, y: 200 });
    const noteB = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 300, y: 400 });
    useGraphStore.getState().setParam(noteA, "anchor_id", targetId);
    useGraphStore.getState().setParam(noteB, "anchor_id", targetId);

    render(<Canvas />);

    expect(screen.getAllByTestId("note-anchor-line")).toHaveLength(2);
  });
});
