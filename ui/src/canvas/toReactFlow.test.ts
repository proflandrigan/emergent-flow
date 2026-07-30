import { describe, expect, test } from "vitest";

import type { EdgeModel, NodeModel } from "../store/model";
import { applyGroupNesting, computeGroupBounds, toAbsolutePosition, toRFEdge, toRFNode } from "./toReactFlow";

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

describe("computeGroupBounds", () => {
  test("two members at known positions produce the expected {x, y, width, height} with padding applied", () => {
    const members: NodeModel[] = [
      {
        id: "m1",
        type: "data.load_csv",
        label: "CSV 1",
        paradigm: "functional",
        params: [],
        ports: [],
        position: { x: 100, y: 100 },
        groupId: "g1",
      },
      {
        id: "m2",
        type: "data.load_csv",
        label: "CSV 2",
        paradigm: "functional",
        params: [],
        ports: [],
        position: { x: 350, y: 250 },
        groupId: "g1",
      },
    ];

    const bounds = computeGroupBounds(members);

    // minX = 100, minY = 100, maxX = 350 + 200 = 550, maxY = 250 + 100 = 350
    // x = 100 - 40 = 60, y = 100 - 40 = 60
    // width = max(240, 550 - 100 + 80) = max(240, 530) = 530
    // height = max(160, 350 - 100 + 80) = max(160, 330) = 330
    expect(bounds).toEqual({
      x: 60,
      y: 60,
      width: 530,
      height: 330,
    });
  });

  test("a single member still respects the MIN_GROUP_WIDTH/MIN_GROUP_HEIGHT floor", () => {
    const members: NodeModel[] = [
      {
        id: "m1",
        type: "data.load_csv",
        label: "CSV 1",
        paradigm: "functional",
        params: [],
        ports: [],
        position: { x: 0, y: 0 },
        groupId: "g1",
      },
    ];

    const bounds = computeGroupBounds(members);

    // minX = 0, minY = 0, maxX = 200, maxY = 100
    // x = 0 - 40 = -40, y = 0 - 40 = -40
    // width = max(240, 200 - 0 + 80) = max(240, 280) = 280
    // height = max(160, 100 - 0 + 80) = max(160, 180) = 180
    expect(bounds.width).toBeGreaterThanOrEqual(240);
    expect(bounds.height).toBeGreaterThanOrEqual(160);
  });

  test("an empty array returns a zero-origin default without throwing", () => {
    const bounds = computeGroupBounds([]);

    expect(bounds).toEqual({
      x: 0,
      y: 0,
      width: 240,
      height: 160,
    });
  });
});

describe("applyGroupNesting", () => {
  test("a group with members gets its position/size from computeGroupBounds and zIndex -1", () => {
    const member1: NodeModel = {
      id: "m1",
      type: "data.load_csv",
      label: "CSV 1",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 100, y: 100 },
      groupId: "g1",
    };
    const member2: NodeModel = {
      id: "m2",
      type: "data.load_csv",
      label: "CSV 2",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 350, y: 250 },
      groupId: "g1",
    };
    const group: NodeModel = groupModel({ id: "g1" });
    const nodeModels = [member1, member2, group];

    const rfNodes = nodeModels.map((n) => toRFNode(n, false, null, null, null, null));
    const result = applyGroupNesting(nodeModels, rfNodes);

    const groupRf = result.find((n) => n.id === "g1");
    expect(groupRf).toBeDefined();
    expect(groupRf?.zIndex).toBe(-1);
    expect(groupRf?.style).toBeDefined();
    expect(typeof groupRf?.style?.width).toBe("number");
    expect(typeof groupRf?.style?.height).toBe("number");
  });

  test("each member gets parentId, extent: parent, and position relative to group bounds", () => {
    const member1: NodeModel = {
      id: "m1",
      type: "data.load_csv",
      label: "CSV 1",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 100, y: 100 },
      groupId: "g1",
    };
    const member2: NodeModel = {
      id: "m2",
      type: "data.load_csv",
      label: "CSV 2",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 350, y: 250 },
      groupId: "g1",
    };
    const group: NodeModel = groupModel({ id: "g1" });
    const nodeModels = [member1, member2, group];

    const rfNodes = nodeModels.map((n) => toRFNode(n, false, null, null, null, null));
    const result = applyGroupNesting(nodeModels, rfNodes);

    const m1Rf = result.find((n) => n.id === "m1");
    expect(m1Rf?.parentId).toBe("g1");
    expect(m1Rf?.extent).toBe("parent");
    expect(m1Rf?.position).toBeDefined();
    // position should be member.position - bounds.x/y
    const bounds = computeGroupBounds([member1, member2]);
    expect(m1Rf?.position).toEqual({
      x: member1.position.x - bounds.x,
      y: member1.position.y - bounds.y,
    });
  });

  test("an ungrouped node passes through unchanged", () => {
    const ungrouped: NodeModel = {
      id: "n1",
      type: "data.load_csv",
      label: "CSV",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 0, y: 0 },
      groupId: null,
    };
    const nodeModels = [ungrouped];

    const rfNodes = nodeModels.map((n) => toRFNode(n, false, null, null, null, null));
    const result = applyGroupNesting(nodeModels, rfNodes);

    const resultNode = result.find((n) => n.id === "n1");
    expect(resultNode).toBe(rfNodes[0]); // exact same object
  });

  test("a node whose groupId points at a non-existent id passes through unchanged", () => {
    const member: NodeModel = {
      id: "m1",
      type: "data.load_csv",
      label: "CSV",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 100, y: 100 },
      groupId: "nonexistent",
    };
    const nodeModels = [member];

    const rfNodes = nodeModels.map((n) => toRFNode(n, false, null, null, null, null));
    const result = applyGroupNesting(nodeModels, rfNodes);

    const resultNode = result.find((n) => n.id === "m1");
    expect(resultNode?.parentId).toBeUndefined();
  });

  test("a group with zero current members passes through unchanged", () => {
    const group: NodeModel = groupModel({ id: "g1" });
    const nodeModels = [group];

    const rfNodes = nodeModels.map((n) => toRFNode(n, false, null, null, null, null));
    const result = applyGroupNesting(nodeModels, rfNodes);

    const resultGroup = result.find((n) => n.id === "g1");
    expect(resultGroup?.zIndex).toBeUndefined();
  });
});

describe("toAbsolutePosition", () => {
  test("a member's relative position converts back to the correct absolute position", () => {
    const member1: NodeModel = {
      id: "m1",
      type: "data.load_csv",
      label: "CSV 1",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 100, y: 100 },
      groupId: "g1",
    };
    const member2: NodeModel = {
      id: "m2",
      type: "data.load_csv",
      label: "CSV 2",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 350, y: 250 },
      groupId: "g1",
    };
    const group: NodeModel = groupModel({ id: "g1" });
    const nodeModels = [member1, member2, group];

    const bounds = computeGroupBounds([member1, member2]);
    const relativePosition = {
      x: member1.position.x - bounds.x,
      y: member1.position.y - bounds.y,
    };

    const absolutePosition = toAbsolutePosition(nodeModels, "m1", relativePosition);

    expect(absolutePosition).toEqual({
      x: member1.position.x,
      y: member1.position.y,
    });
  });

  test("an ungrouped node's position passes through unchanged", () => {
    const ungrouped: NodeModel = {
      id: "n1",
      type: "data.load_csv",
      label: "CSV",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 0, y: 0 },
      groupId: null,
    };
    const nodeModels = [ungrouped];

    const absolutePosition = toAbsolutePosition(nodeModels, "n1", { x: 50, y: 60 });

    expect(absolutePosition).toEqual({ x: 50, y: 60 });
  });

  test("a node whose groupId points at a non-existent node passes through unchanged", () => {
    const member: NodeModel = {
      id: "m1",
      type: "data.load_csv",
      label: "CSV",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 100, y: 100 },
      groupId: "nonexistent",
    };
    const nodeModels = [member];

    const absolutePosition = toAbsolutePosition(nodeModels, "m1", { x: 50, y: 60 });

    expect(absolutePosition).toEqual({ x: 50, y: 60 });
  });
});
