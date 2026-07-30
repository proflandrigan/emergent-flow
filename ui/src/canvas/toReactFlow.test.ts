import { describe, expect, test } from "vitest";

import type { EdgeModel, NodeModel } from "../store/model";
import { toRFEdge, toRFNode } from "./toReactFlow";

const edge: EdgeModel = {
  id: "e1",
  source: { node_id: "a", port_id: "pa" },
  target: { node_id: "b", port_id: "pb" },
};

describe("toRFEdge", () => {
  test("compatible === false marks the edge incompatible and carries the reason", () => {
    const rfEdge = toRFEdge(edge, false, false, "Expected int, got str");

    expect(rfEdge.type).toBe("efEdge");
    expect(rfEdge.source).toBe("a");
    expect(rfEdge.sourceHandle).toBe("pa");
    expect(rfEdge.target).toBe("b");
    expect(rfEdge.targetHandle).toBe("pb");
    expect(rfEdge.data?.incompatible).toBe(true);
    expect(rfEdge.data?.reason).toBe("Expected int, got str");
  });

  test("null verdict (unknown) does not mark the edge incompatible", () => {
    const rfEdge = toRFEdge(edge, false, null, null);

    expect(rfEdge.data?.incompatible).toBe(false);
  });

  test("undefined verdict (not yet validated) does not mark the edge incompatible", () => {
    const rfEdge = toRFEdge(edge, false, undefined, undefined);

    expect(rfEdge.data?.incompatible).toBe(false);
  });

  test("selected flag passes through", () => {
    const rfEdge = toRFEdge(edge, true, undefined, undefined);

    expect(rfEdge.selected).toBe(true);
  });
});

function noteModel(overrides?: Partial<NodeModel>): NodeModel {
  return {
    id: "n1",
    type: "notes.markdown",
    label: undefined,
    paradigm: "functional",
    params: [
      { name: "content", typeToken: "str", value: "# Hello\nThis is a note." },
      { name: "color", typeToken: "str", value: "pink" },
      { name: "anchor_id", typeToken: "str | null", value: "node-abc" },
    ],
    ports: [],
    position: { x: 100, y: 200 },
    ...overrides,
  };
}

describe("toRFNode (notes.markdown)", () => {
  test("produces a noteNode with content / color / anchorId from params", () => {
    const rf = toRFNode(noteModel(), false, null, null, null, null) as ReturnType<typeof toRFNode>;

    expect(rf.type).toBe("noteNode");
    if (rf.type === "noteNode") {
      expect(rf.data.content).toBe("# Hello\nThis is a note.");
      expect(rf.data.color).toBe("pink");
      expect(rf.data.anchorId).toBe("node-abc");
    }
  });

  test("missing color param falls back to yellow", () => {
    const rf = toRFNode(
      noteModel({ params: [{ name: "content", typeToken: "str", value: "hi" }] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "noteNode") {
      expect(rf.data.color).toBe("yellow");
    }
  });

  test("non-string color value falls back to yellow", () => {
    const rf = toRFNode(
      noteModel({ params: [
        { name: "content", typeToken: "str", value: "hi" },
        { name: "color", typeToken: "str", value: 42 },
      ] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "noteNode") {
      expect(rf.data.color).toBe("yellow");
    }
  });

  test("missing anchor_id param produces null anchorId", () => {
    const rf = toRFNode(
      noteModel({ params: [
        { name: "content", typeToken: "str", value: "hi" },
        { name: "color", typeToken: "str", value: "blue" },
      ] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "noteNode") {
      expect(rf.data.anchorId).toBeNull();
    }
  });

  test("null anchor_id value produces null anchorId", () => {
    const rf = toRFNode(
      noteModel({ params: [
        { name: "content", typeToken: "str", value: "hi" },
        { name: "color", typeToken: "str", value: "blue" },
        { name: "anchor_id", typeToken: "str | null", value: null },
      ] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "noteNode") {
      expect(rf.data.anchorId).toBeNull();
    }
  });

  test("noteNode passes id / position / selected through", () => {
    const rf = toRFNode(noteModel(), true, null, null, null, null) as ReturnType<typeof toRFNode>;

    expect(rf.id).toBe("n1");
    expect(rf.position).toEqual({ x: 100, y: 200 });
    expect(rf.selected).toBe(true);
  });
});

function groupModel(overrides?: Partial<NodeModel>): NodeModel {
  return {
    id: "g1",
    type: "layout.group",
    label: undefined,
    paradigm: "functional",
    params: [
      { name: "label", typeToken: "str", value: "My Group" },
      { name: "color", typeToken: "str", value: "blue" },
    ],
    ports: [],
    position: { x: 100, y: 200 },
    ...overrides,
  };
}

describe("toRFNode (layout.group)", () => {
  test("produces a groupNode with label / color from params", () => {
    const rf = toRFNode(groupModel(), false, null, null, null, null) as ReturnType<typeof toRFNode>;

    expect(rf.type).toBe("groupNode");
    if (rf.type === "groupNode") {
      expect(rf.data.label).toBe("My Group");
      expect(rf.data.color).toBe("blue");
    }
  });

  test("missing color param falls back to slate", () => {
    const rf = toRFNode(
      groupModel({ params: [{ name: "label", typeToken: "str", value: "Test" }] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "groupNode") {
      expect(rf.data.color).toBe("slate");
    }
  });

  test("non-string color value falls back to slate", () => {
    const rf = toRFNode(
      groupModel({ params: [
        { name: "label", typeToken: "str", value: "Test" },
        { name: "color", typeToken: "str", value: 42 },
      ] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "groupNode") {
      expect(rf.data.color).toBe("slate");
    }
  });

  test("missing label param falls back to Group", () => {
    const rf = toRFNode(
      groupModel({ params: [{ name: "color", typeToken: "str", value: "green" }] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "groupNode") {
      expect(rf.data.label).toBe("Group");
    }
  });

  test("non-string label value falls back to Group", () => {
    const rf = toRFNode(
      groupModel({ params: [
        { name: "label", typeToken: "str", value: 42 },
        { name: "color", typeToken: "str", value: "green" },
      ] }),
      false, null, null, null, null,
    ) as ReturnType<typeof toRFNode>;

    if (rf.type === "groupNode") {
      expect(rf.data.label).toBe("Group");
    }
  });

  test("groupNode passes id / position / selected through", () => {
    const rf = toRFNode(groupModel(), true, null, null, null, null) as ReturnType<typeof toRFNode>;

    expect(rf.id).toBe("g1");
    expect(rf.position).toEqual({ x: 100, y: 200 });
    expect(rf.selected).toBe(true);
  });
});
