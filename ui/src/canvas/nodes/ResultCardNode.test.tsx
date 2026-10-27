import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { useExecutionStore } from "../../store/executionStore";
import { useGraphStore } from "../../store/graphStore";
import { parseBlocks } from "../resultCardBlocks";
import type { ResultCardBlock } from "../resultCardBlocks";
import {
  ResultCardNode,
  type ResultCardNodeData,
  type ResultCardNodeType,
} from "./ResultCardNode";

function makeProps(id: string, data: ResultCardNodeData): NodeProps<ResultCardNodeType> {
  return {
    id,
    data,
    selected: false,
    type: "resultCardNode",
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as unknown as NodeProps<ResultCardNodeType>;
}

function renderCard(blocks: ResultCardBlock[], title = "My Card") {
  const data: ResultCardNodeData = { title, blocks, width: 480, inPortId: null };
  return render(
    <ReactFlowProvider>
      <ResultCardNode {...makeProps("rc1", data)} />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useExecutionStore.setState({ results: {}, statuses: {}, runMeta: null });
  useGraphStore.getState().reset();
});

function seedGraph(blocks: ResultCardBlock[]): void {
  useGraphStore.setState({
    nodes: {
      card1: {
        id: "card1",
        type: "reports.result_card",
        paradigm: "functional",
        position: { x: 0, y: 0 },
        params: [
          { name: "title", typeToken: "str", value: "My Card" },
          { name: "blocks_json", typeToken: "str", value: JSON.stringify(blocks) },
          { name: "width", typeToken: "int", value: 480 },
        ],
        ports: [
          { id: "in1", name: "inputs", direction: "in", dataType: "any", cardinality: "many" },
        ],
      },
      src: {
        id: "src",
        type: "data.load",
        paradigm: "functional",
        position: { x: 0, y: 0 },
        params: [],
        ports: [
          { id: "p1", name: "out", direction: "out", dataType: "any", cardinality: "one" },
        ],
      },
    },
    edges: {
      e1: {
        id: "e1",
        source: { node_id: "src", port_id: "p1" },
        target: { node_id: "card1", port_id: "in1" },
      },
    },
  });
}

function renderEditing(blocks: ResultCardBlock[]) {
  seedGraph(blocks);
  const data: ResultCardNodeData = { title: "My Card", blocks, width: 480, inPortId: "in1" };
  const view = render(
    <ReactFlowProvider>
      <ResultCardNode {...makeProps("card1", data)} />
    </ReactFlowProvider>,
  );
  fireEvent.click(screen.getByTestId("result-card-edit-toggle"));
  return view;
}

function storedBlocks(): ResultCardBlock[] {
  const param = useGraphStore
    .getState()
    .nodes.card1?.params.find((p) => p.name === "blocks_json");
  return parseBlocks(param?.value);
}

describe("ResultCardNode", () => {
  test("renders the title", () => {
    renderCard([]);
    expect(screen.getByTestId("result-card-title")).toHaveTextContent("My Card");
  });

  test("renders markdown block text", () => {
    renderCard([{ kind: "markdown", text: "# Heading\n\nsome prose" }]);
    expect(screen.getByText("Heading")).toBeInTheDocument();
    expect(screen.getByText("some prose")).toBeInTheDocument();
  });

  test("renders a result block payload", () => {
    useExecutionStore.setState({
      results: { n1: { out: { kind: "scalar", value: 42 } } },
    });
    renderCard([{ kind: "result", source: "n1:out", caption: "the answer" }]);
    expect(screen.getByTestId("payload-scalar")).toHaveTextContent("42");
    expect(screen.getByTestId("result-card-caption")).toHaveTextContent("the answer");
  });

  test("shows a pending message when there is no result", () => {
    renderCard([{ kind: "result", source: "n1:out", caption: "" }]);
    expect(screen.getByTestId("result-card-pending")).toHaveTextContent(/Not run yet/);
  });

  test("shows an error message when the source node failed", () => {
    useExecutionStore.setState({
      statuses: { n1: { status: "error", error: "boom" } },
    });
    renderCard([{ kind: "result", source: "n1:out", caption: "" }]);
    expect(screen.getByTestId("result-card-error")).toHaveTextContent("Source failed");
  });

  test("shows run id and timestamp evidence under an ok result only", () => {
    useExecutionStore.setState({
      results: { n1: { out: { kind: "scalar", value: 42 } } },
      runMeta: { runId: "2026-07-30T14-02-11Z-ab12", finishedAt: "2026-07-30T14:02:11+00:00" },
    });
    renderCard([{ kind: "result", source: "n1:out", caption: "" }]);
    expect(screen.getByTestId("result-card-evidence")).toHaveTextContent(
      "Run ab12 \u00b7 2026-07-30T14:02:11+00:00",
    );
    expect(screen.getByTestId("result-card-evidence")).toHaveAttribute(
      "title",
      "Run ID: 2026-07-30T14-02-11Z-ab12",
    );
  });

  test("shows no evidence when the block is not ok", () => {
    useExecutionStore.setState({
      runMeta: { runId: "r", finishedAt: "2026-07-30T14:02:11+00:00" },
    });
    renderCard([{ kind: "result", source: "n1:out", caption: "" }]);
    expect(screen.queryByTestId("result-card-evidence")).toBeNull();
  });

  test("shows the empty-card placeholder", () => {
    renderCard([]);
    expect(screen.getByTestId("result-card-empty")).toBeInTheDocument();
  });

  describe("editing", () => {
    const two: ResultCardBlock[] = [
      { kind: "markdown", text: "first" },
      { kind: "markdown", text: "second" },
    ];

    test("edit toggle shows the add-result select with the upstream option", () => {
      renderEditing([]);
      const select = screen.getByTestId("result-card-add-result");
      expect(select).toBeEnabled();
      expect(screen.getByRole("option", { name: /out/ })).toHaveValue("src:out");
    });

    test("choosing an upstream result appends a result block", () => {
      renderEditing([]);
      fireEvent.change(screen.getByTestId("result-card-add-result"), {
        target: { value: "src:out" },
      });
      expect(storedBlocks()).toEqual([{ kind: "result", source: "src:out", caption: "" }]);
    });

    test("Add text appends a markdown block", () => {
      renderEditing([]);
      fireEvent.click(screen.getByTestId("result-card-add-text"));
      expect(storedBlocks()).toEqual([{ kind: "markdown", text: "" }]);
    });

    test("Remove deletes a block", () => {
      renderEditing(two);
      fireEvent.click(screen.getAllByLabelText("Remove")[0] as HTMLElement);
      expect(storedBlocks()).toEqual([{ kind: "markdown", text: "second" }]);
    });

    test("Move down reorders blocks", () => {
      renderEditing(two);
      fireEvent.click(screen.getAllByLabelText("Move down")[0] as HTMLElement);
      expect(storedBlocks()).toEqual([
        { kind: "markdown", text: "second" },
        { kind: "markdown", text: "first" },
      ]);
    });

    test("blur on the title input updates the title param", () => {
      renderEditing([]);
      const input = screen.getByTestId("result-card-title-input");
      fireEvent.change(input, { target: { value: "Renamed" } });
      fireEvent.blur(input);
      const title = useGraphStore
        .getState()
        .nodes.card1?.params.find((p) => p.name === "title");
      expect(title?.value).toBe("Renamed");
    });
  });
});
