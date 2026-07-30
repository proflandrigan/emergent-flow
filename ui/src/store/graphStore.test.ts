import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import type { Graph } from "../generated/ir";
import catalog from "../generated/catalog.json";
import { useGraphStore } from "./graphStore";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const loadCsv = requireCatalogNode("data.load_csv");

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("addNodeFromSpec", () => {
  test("adds a node seeded from the catalog spec", () => {
    const nodeId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(1);

    const node = nodes[nodeId];
    expect(node.type).toBe("data.load_csv");
    expect(node.ports).toHaveLength(loadCsv.ports.length);
    for (const port of node.ports) {
      expect(port.id).toBeTruthy();
    }
    expect(node.params).toHaveLength(loadCsv.params.length);
    const pathParam = node.params.find((p) => p.name === "path");
    expect(pathParam?.value).toBe(
      loadCsv.params.find((p) => p.name === "path")?.default ?? null,
    );
    const encodingParam = node.params.find((p) => p.name === "encoding");
    expect(encodingParam?.value).toBe("utf-8");
    expect(encodingParam?.default).toBe("utf-8");
  });

  test("adding twice produces two distinct node ids", () => {
    const id1 = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const id2 = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 10, y: 10 });

    expect(id1).not.toBe(id2);
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(2);
  });
});

describe("connect", () => {
  function addTwoConnectableNodes() {
    const sourceId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    // load_csv only has an out port; reuse it as a fake target too so we have an in-shaped
    // port to connect to without depending on a second catalog entry's exact shape.
    const targetId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 100, y: 0 });
    const sourcePort = useGraphStore.getState().nodes[sourceId].ports[0];
    const targetPort = useGraphStore.getState().nodes[targetId].ports[0];
    return {
      sourceId,
      targetId,
      source: { node_id: sourceId, port_id: sourcePort.id },
      target: { node_id: targetId, port_id: targetPort.id },
    };
  }

  test("connects two ports and shows up in toIR()", () => {
    const { source, target } = addTwoConnectableNodes();

    const edgeId = useGraphStore.getState().connect(source, target);
    expect(edgeId).not.toBeNull();

    const graph = useGraphStore.getState().toIR();
    const edges = Object.entries(graph.edges ?? {});
    expect(edges).toHaveLength(1);
    const [id, edge] = edges[0];
    expect(id).toBe(edgeId);
    expect(edge.source).toEqual(source);
    expect(edge.target).toEqual(target);
  });

  test("a duplicate connect returns null and does not add a second edge", () => {
    const { source, target } = addTwoConnectableNodes();

    const firstId = useGraphStore.getState().connect(source, target);
    const secondId = useGraphStore.getState().connect(source, target);

    expect(firstId).not.toBeNull();
    expect(secondId).toBeNull();
    expect(Object.keys(useGraphStore.getState().edges)).toHaveLength(1);
  });
});

describe("removeNode", () => {
  test("deletes the node and any incident edges", () => {
    const sourceId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const targetId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 100, y: 0 });
    const sourcePort = useGraphStore.getState().nodes[sourceId].ports[0];
    const targetPort = useGraphStore.getState().nodes[targetId].ports[0];
    useGraphStore
      .getState()
      .connect(
        { node_id: sourceId, port_id: sourcePort.id },
        { node_id: targetId, port_id: targetPort.id },
      );

    useGraphStore.getState().removeNode(sourceId);

    const { nodes, edges } = useGraphStore.getState();
    expect(nodes[sourceId]).toBeUndefined();
    expect(nodes[targetId]).toBeDefined();
    expect(Object.keys(edges)).toHaveLength(0);
  });
});

describe("toIR", () => {
  test("produces a Graph whose nodes/edges maps are keyed by id", () => {
    const sourceId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const targetId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 100, y: 0 });
    const sourcePort = useGraphStore.getState().nodes[sourceId].ports[0];
    const targetPort = useGraphStore.getState().nodes[targetId].ports[0];
    useGraphStore
      .getState()
      .connect(
        { node_id: sourceId, port_id: sourcePort.id },
        { node_id: targetId, port_id: targetPort.id },
      );

    const graph = useGraphStore.getState().toIR();

    expect(Object.keys(graph.nodes ?? {}).sort()).toEqual(
      [sourceId, targetId].sort(),
    );
    expect(Object.keys(graph.edges ?? {})).toHaveLength(1);
    for (const [id, node] of Object.entries(graph.nodes ?? {})) {
      expect(node.id).toBe(id);
    }
    for (const [id, edge] of Object.entries(graph.edges ?? {})) {
      expect(edge.id).toBe(id);
    }
  });
});

describe("loadIR", () => {
  test("two nodes at the same IR position get distinct canvas positions", () => {
    const graph: Graph = {
      paradigm: "functional",
      nodes: {
        a: {
          id: "a",
          type: "data.load_csv",
          paradigm: "functional",
          params: [],
          ports: [{ name: "out", direction: "out" }],
          position: { x: 0, y: 0 },
        },
        b: {
          id: "b",
          type: "data.load_csv",
          paradigm: "functional",
          params: [],
          ports: [{ name: "out", direction: "out" }],
          position: { x: 0, y: 0 },
        },
      },
      edges: {},
    };

    useGraphStore.getState().loadIR(graph);

    const { nodes } = useGraphStore.getState();
    expect(nodes.a.position).not.toEqual(nodes.b.position);
  });
});

describe("pasteNodes", () => {
  test("pasting one node produces a new node with different id, same type/params (deep-equal), offset position, and fresh port ids", () => {
    const originalId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 100, y: 200 });
    const original = useGraphStore.getState().nodes[originalId];

    const [pastedId] = useGraphStore.getState().pasteNodes([original]);
    const pasted = useGraphStore.getState().nodes[pastedId];

    expect(pasted.id).not.toBe(original.id);
    expect(pasted.type).toBe(original.type);
    expect(pasted.params).toEqual(original.params);
    expect(pasted.params).not.toBe(original.params);
    expect(pasted.position.x).toBe(original.position.x + 40);
    expect(pasted.position.y).toBe(original.position.y + 40);

    for (const port of pasted.ports) {
      expect(port.id).toBeTruthy();
      const origPort = original.ports.find((p) => p.name === port.name);
      expect(origPort).toBeDefined();
      expect(port.id).not.toBe(origPort!.id);
    }
  });

  test("mutating pasted node's params does not affect original", () => {
    const originalId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const original = useGraphStore.getState().nodes[originalId];

    const [pastedId] = useGraphStore.getState().pasteNodes([original]);

    useGraphStore.getState().setParam(originalId, original.params[0].name, "mutated");

    const reloadedPasted = useGraphStore.getState().nodes[pastedId];
    expect(reloadedPasted.params[0].value).not.toBe("mutated");
  });

  test("pasting the same node twice produces two distinct new ids each time", () => {
    const originalId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const original = useGraphStore.getState().nodes[originalId];

    const [id1] = useGraphStore.getState().pasteNodes([original]);
    const [id2] = useGraphStore.getState().pasteNodes([original]);

    expect(id1).not.toBe(id2);
    expect(id1).not.toBe(originalId);
    expect(id2).not.toBe(originalId);
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(3);
  });

  test("pasting the same clipboard twice in a row does not stack the two new nodes on each other", () => {
    // Regression: pasteNodes always offsets from the *original* clipboard model, so two
    // successive Ctrl+V calls (clipboard unchanged between them, as Canvas.tsx does it)
    // used to land both new nodes on the exact same coordinates.
    const originalId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const original = useGraphStore.getState().nodes[originalId];

    const [id1] = useGraphStore.getState().pasteNodes([original]);
    const [id2] = useGraphStore.getState().pasteNodes([original]);

    const pos1 = useGraphStore.getState().nodes[id1].position;
    const pos2 = useGraphStore.getState().nodes[id2].position;
    expect(pos1).not.toEqual(pos2);
  });

  test("pasting an empty array returns [] and does not change nodes or push a history entry", () => {
    useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const beforeUndo = useGraphStore.getState().canUndo();

    const result = useGraphStore.getState().pasteNodes([]);

    expect(result).toEqual([]);
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);
    expect(useGraphStore.getState().canUndo()).toBe(beforeUndo);
  });
});

describe("groupSelection / ungroupSelection", () => {
  test("grouping 2+ nodes creates a layout.group node and sets groupId on all members", () => {
    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 0 });

    const groupId = useGraphStore.getState().groupSelection([n1, n2]);

    expect(groupId).not.toBeNull();
    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(3); // 2 members + 1 group
    expect(nodes[groupId!].type).toBe("layout.group");
    expect(nodes[n1].groupId).toBe(groupId);
    expect(nodes[n2].groupId).toBe(groupId);
  });

  test("grouping fewer than 2 ids is a no-op and returns null", () => {
    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const beforeUndo = useGraphStore.getState().canUndo();

    const groupId = useGraphStore.getState().groupSelection([n1]);

    expect(groupId).toBeNull();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);
    expect(useGraphStore.getState().canUndo()).toBe(beforeUndo);
  });

  test("grouping with empty array is a no-op and returns null", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const beforeUndo = useGraphStore.getState().canUndo();

    const groupId = useGraphStore.getState().groupSelection([]);

    expect(groupId).toBeNull();
    expect(useGraphStore.getState().canUndo()).toBe(beforeUndo);
  });

  test("ungrouping via a member's id clears groupId on all members and removes the group node", () => {
    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 0 });
    const groupId = useGraphStore.getState().groupSelection([n1, n2])!;

    useGraphStore.getState().ungroupSelection([n1]);

    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(2); // group node deleted
    expect(nodes[n1].groupId).toBeNull();
    expect(nodes[n2].groupId).toBeNull();
    expect(nodes[groupId]).toBeUndefined();
  });

  test("ungrouping via the group node's own id has the same effect", () => {
    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 0 });
    const groupId = useGraphStore.getState().groupSelection([n1, n2])!;

    useGraphStore.getState().ungroupSelection([groupId]);

    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(2); // group node deleted
    expect(nodes[n1].groupId).toBeNull();
    expect(nodes[n2].groupId).toBeNull();
    expect(nodes[groupId]).toBeUndefined();
  });

  test("ungrouping when nothing is grouped is a no-op with no history entry", () => {
    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const beforeUndo = useGraphStore.getState().canUndo();

    useGraphStore.getState().ungroupSelection([n1]);

    expect(useGraphStore.getState().canUndo()).toBe(beforeUndo);
  });

  test("grouping pushes exactly one history entry", () => {
    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 0 });

    useGraphStore.getState().groupSelection([n1, n2]);

    expect(useGraphStore.getState().canUndo()).toBe(true);
    // Undo should restore the pre-group state
    useGraphStore.getState().undo();
    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(2);
    for (const node of Object.values(nodes)) {
      expect(node.groupId).toBeNull();
    }
  });
});
