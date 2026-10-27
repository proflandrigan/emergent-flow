import { ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../../catalog/types";
import catalog from "../../generated/catalog.json";
import { useGraphStore } from "../../store/graphStore";
import { NoteNode, type NoteNodeData } from "./NoteNode";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const markdownNote = requireCatalogNode("notes.markdown");

type NoteNodeType = Node<NoteNodeData, "noteNode">;

function makeProps(id: string, data: NoteNodeData): NodeProps<NoteNodeType> {
  return {
    id,
    data,
    selected: false,
    type: "noteNode",
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as unknown as NodeProps<NoteNodeType>;
}

function renderNoteNode(id: string, data: NoteNodeData) {
  return render(
    <ReactFlowProvider>
      <NoteNode {...makeProps(id, data)} />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("NoteNode", () => {
  test("renders markdown content", () => {
    renderNoteNode("n1", {
      content: "# Heading\n\n- item one\n- item two",
      color: "yellow",
      anchorId: null,
    });

    expect(screen.getByText("Heading")).toBeInTheDocument();
    expect(screen.getByText("item one")).toBeInTheDocument();
    expect(screen.getByText("item two")).toBeInTheDocument();
  });

  test("empty content shows the placeholder prompt", () => {
    renderNoteNode("n1", { content: "", color: "yellow", anchorId: null });

    expect(screen.getByText(/Double-click to add a note/)).toBeInTheDocument();
    expect(screen.queryByTestId("note-node-editor")).not.toBeInTheDocument();
  });

  test("color param controls the background swatch", () => {
    renderNoteNode("n1", { content: "hi", color: "pink", anchorId: null });

    expect(screen.getByTestId("note-node").style.background).toBe(
      "rgb(252, 231, 243)",
    );
  });

  test("legacy data without kind shows no open-question badge", () => {
    renderNoteNode("n1", { content: "hi", color: "yellow", anchorId: null });

    expect(screen.queryByTestId("open-question-badge")).not.toBeInTheDocument();
  });

  test("open-question kind shows the badge regardless of color", () => {
    renderNoteNode("n1", {
      content: "why?",
      color: "yellow",
      anchorId: null,
      kind: "open-question",
    });

    expect(screen.getByTestId("open-question-badge").textContent).toContain("Open question");
    expect(screen.getByTestId("note-node").getAttribute("data-kind")).toBe("open-question");
    expect(screen.getByRole("note", { name: "Open question" })).toBeInTheDocument();
  });

  test("orange ordinary note uses the orange swatch and no badge", () => {
    renderNoteNode("n1", { content: "hi", color: "orange", anchorId: null, kind: "note" });

    expect(screen.queryByTestId("open-question-badge")).not.toBeInTheDocument();
    expect(screen.getByTestId("note-node").style.background).toBe("rgb(255, 237, 213)");
  });

  test("open question still enters edit mode and keeps the badge", () => {
    renderNoteNode("n1", {
      content: "why?",
      color: "yellow",
      anchorId: null,
      kind: "open-question",
    });

    fireEvent.doubleClick(screen.getByTestId("note-node-preview"));

    expect(screen.getByTestId("note-node-editor")).toBeInTheDocument();
    expect(screen.getByTestId("open-question-badge")).toBeInTheDocument();
  });

  test("anchor to a missing id shows the unavailable line and keeps the note", () => {
    renderNoteNode("n1", { content: "still here", color: "yellow", anchorId: "ghost" });

    expect(screen.getByTestId("note-anchor-missing")).toBeInTheDocument();
    expect(screen.getByText("still here")).toBeInTheDocument();
  });

  test("anchor to an existing node does not show the unavailable line", () => {
    const anchorId = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 0, y: 0 });

    renderNoteNode("n1", { content: "hi", color: "yellow", anchorId });

    expect(screen.queryByTestId("note-anchor-missing")).not.toBeInTheDocument();
  });

  test("unknown color falls back to the yellow swatch", () => {
    renderNoteNode("n1", { content: "hi", color: "not-a-real-color", anchorId: null });

    expect(screen.getByTestId("note-node").style.background).toBe(
      "rgb(254, 243, 199)",
    );
  });

  test("double-click enters edit mode, and blur commits the change to the store", () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 0, y: 0 });
    useGraphStore.getState().setParam(nodeId, "content", "original text");

    renderNoteNode(nodeId, { content: "original text", color: "yellow", anchorId: null });

    fireEvent.doubleClick(screen.getByTestId("note-node-preview"));

    const editor = screen.getByTestId("note-node-editor");
    fireEvent.change(editor, { target: { value: "edited text" } });
    fireEvent.blur(editor);

    expect(screen.queryByTestId("note-node-editor")).not.toBeInTheDocument();
    const stored = useGraphStore
      .getState()
      .nodes[nodeId].params.find((p) => p.name === "content");
    expect(stored?.value).toBe("edited text");
  });

  test("Escape cancels the edit without committing", () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(markdownNote, { x: 0, y: 0 });
    useGraphStore.getState().setParam(nodeId, "content", "original text");

    renderNoteNode(nodeId, { content: "original text", color: "yellow", anchorId: null });

    fireEvent.doubleClick(screen.getByTestId("note-node-preview"));
    const editor = screen.getByTestId("note-node-editor");
    fireEvent.change(editor, { target: { value: "throwaway edit" } });
    fireEvent.keyDown(editor, { key: "Escape" });

    expect(screen.queryByTestId("note-node-editor")).not.toBeInTheDocument();
    const stored = useGraphStore
      .getState()
      .nodes[nodeId].params.find((p) => p.name === "content");
    expect(stored?.value).toBe("original text");
  });
});
