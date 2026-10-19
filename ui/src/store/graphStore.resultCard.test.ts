import { beforeEach, describe, expect, test } from "vitest";

import { parseBlocks } from "../canvas/resultCardBlocks";
import { useGraphStore } from "./graphStore";
import type { NodeModel } from "./model";

function makeNode(id: string, x: number, y: number): NodeModel {
  return {
    id,
    type: "data.fake",
    label: id,
    paradigm: "functional",
    params: [],
    ports: [
      {
        id: `${id}-out`,
        name: "out",
        direction: "out",
        dataType: "any",
        cardinality: "one",
      },
    ],
    position: { x, y },
    groupId: null,
  };
}

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("createResultCardForSelection", () => {
  test("creates a result card wired to the selected nodes", () => {
    useGraphStore.setState({
      nodes: { a: makeNode("a", 0, 0), b: makeNode("b", 0, 200) },
    });

    const cardId = useGraphStore.getState().createResultCardForSelection(["a", "b"]);
    expect(cardId).toBeTruthy();

    const state = useGraphStore.getState();
    const card = state.nodes[cardId as string];
    expect(card.type).toBe("reports.result_card");
    expect(card.params.find((p) => p.name === "title")?.value).toBe("Summary");

    const edges = Object.values(state.edges).filter((e) => e.target.node_id === cardId);
    expect(edges).toHaveLength(2);

    const json = card.params.find((p) => p.name === "blocks_json")?.value;
    const blocks = parseBlocks(json);
    expect(blocks).toHaveLength(3);
    expect(blocks[0].kind).toBe("markdown");
    expect(blocks.slice(1).map((b) => (b.kind === "result" ? b.source : null))).toEqual([
      "a:out",
      "b:out",
    ]);
  });

  test("returns null when nothing eligible is selected", () => {
    expect(useGraphStore.getState().createResultCardForSelection(["missing"])).toBeNull();
  });

  test("is a single undo step; redo restores it", () => {
    useGraphStore.setState({
      nodes: { a: makeNode("a", 0, 0), b: makeNode("b", 0, 200) },
    });
    const cardId = useGraphStore.getState().createResultCardForSelection(["a", "b"]) as string;

    useGraphStore.getState().undo();
    let state = useGraphStore.getState();
    expect(Object.keys(state.nodes).sort()).toEqual(["a", "b"]);
    expect(Object.keys(state.edges)).toHaveLength(0);

    useGraphStore.getState().redo();
    state = useGraphStore.getState();
    expect(state.nodes[cardId]).toBeTruthy();
    expect(Object.values(state.edges).filter((e) => e.target.node_id === cardId)).toHaveLength(2);
  });
});
