import { beforeEach, describe, expect, test } from "vitest";

import catalog from "../generated/catalog.json";
import type { CatalogNode } from "../catalog/types";
import { computeGroupBounds, GROUP_PADDING } from "../canvas/toReactFlow";
import { useGraphStore } from "./graphStore";
import { useSelectionStore } from "./selectionStore";

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
  useSelectionStore.setState({ nodes: {}, edges: {} });
});

// ---------------------------------------------------------------------------
// replaceSelection must clear edge selection state
// ---------------------------------------------------------------------------
describe("replaceSelection", () => {
  test("clears edge selection when replacing node selection", () => {
    useSelectionStore.getState().setEdgeSelected("e1", true);
    useSelectionStore.getState().replaceSelection(["n1"]);
    expect(useSelectionStore.getState().edges).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// addCalloutAroundSelection must account for group node rendered bounds
// ---------------------------------------------------------------------------
describe("addCalloutAroundSelection with group nodes", () => {
  test("uses computed group bounds not stale store position", () => {
    const groupId = "group1";
    const n1 = "n1";
    const n2 = "n2";
    const n3 = "n3";
    const n1Params = loadCsv.params.map((p) => ({
      name: p.name,
      typeToken: p.type_token,
      value: p.default ?? null,
      default: p.default ?? null,
    }));
    const n1Ports = loadCsv.ports.map((p) => ({
      id: `port-${p.name}`,
      name: p.name,
      direction: p.direction,
      dataType: p.data_type ?? "any",
      cardinality: p.cardinality ?? "one",
      label: p.label ?? null,
    }));

    useGraphStore.setState({
      nodes: {
        [n1]: {
          id: n1,
          type: "data.load_csv",
          label: "CSV1",
          paradigm: "functional",
          params: n1Params,
          ports: n1Ports,
          position: { x: 100, y: 0 },
          groupId: groupId,
        },
        [n2]: {
          id: n2,
          type: "data.load_csv",
          label: "CSV2",
          paradigm: "functional",
          params: n1Params,
          ports: n1Ports,
          position: { x: 300, y: 0 },
          groupId: groupId,
        },
        [groupId]: {
          id: groupId,
          type: "layout.group",
          label: "Group",
          paradigm: "functional",
          params: [
            { name: "label", typeToken: "str", value: "Group", default: "Group" },
            { name: "color", typeToken: "str", value: "slate", default: "slate" },
          ],
          ports: [],
          position: { x: 60, y: -40 },
          groupId: null,
        },
      },
      edges: {},
      groupMeta: {},
      past: [],
      future: [],
      _lastTxn: null,
    });

    // Move n1 left — this shifts the group's effective rendered bounds
    useGraphStore.getState().moveNode(n1, { x: 0, y: 0 });

    // Add a third node
    useGraphStore.setState((state) => ({
      nodes: {
        ...state.nodes,
        [n3]: {
          id: n3,
          type: "data.load_csv",
          label: "CSV3",
          paradigm: "functional",
          params: n1Params,
          ports: n1Ports,
          position: { x: 500, y: 0 },
          groupId: null,
        },
      },
    }));

    const calloutId = useGraphStore.getState().addCalloutAroundSelection([groupId, n3]);
    expect(calloutId).not.toBeNull();

    const callout = useGraphStore.getState().nodes[calloutId!];
    const groupStoreX = useGraphStore.getState().nodes[groupId].position.x;
    const groupMembers = Object.values(useGraphStore.getState().nodes).filter(
      (node) => node.groupId === groupId,
    );
    const recomputedGroupX = computeGroupBounds(groupMembers).x;

    // The callout should be positioned relative to the recomputed group bounds,
    // not the stale store position
    expect(callout.position.x).toBe(recomputedGroupX - GROUP_PADDING);
    expect(callout.position.x).toBeLessThan(groupStoreX - GROUP_PADDING);
  });
});

// ---------------------------------------------------------------------------
// Edge selection is preserved when onSelectionChange fires after onEdgesChange.select
// (i.e., the order React Flow uses: onSelectionChange first, then onEdgesChange.select).
// ---------------------------------------------------------------------------
describe("replaceSelection with edge selection interaction", () => {
  test("edge stays selected when setEdgeSelected fires after replaceSelection", () => {
    // Simulates: onSelectionChange fires first (clears edges via replaceSelection),
    // then onEdgesChange.select fires (re-selects the edge).
    useSelectionStore.getState().replaceSelection([]);
    useSelectionStore.getState().setEdgeSelected("e1", true);
    expect(useSelectionStore.getState().edges).toEqual({ e1: true });
  });

  test("node selection clears edges when replaceSelection fires after setEdgeSelected", () => {
    // Simulates: an edge was previously selected, then a node is clicked.
    // onEdgesChange.select may or may not fire, but onSelectionChange fires
    // with the node, and replaceSelection overwrites both.
    useSelectionStore.getState().setEdgeSelected("e1", true);
    useSelectionStore.getState().replaceSelection(["n1"]);
    expect(useSelectionStore.getState().edges).toEqual({});
    expect(useSelectionStore.getState().nodes).toEqual({ n1: true });
  });
});

// ---------------------------------------------------------------------------
// onSelectionChange can fire after onEdgesChange.select, wiping edge selection
// ---------------------------------------------------------------------------
describe("onSelectionChange races with onEdgesChange.select", () => {
  test("edge selection is lost when onSelectionChange fires after onEdgesChange.select", () => {
    // Simulates: user clicks edge e1. React Flow fires:
    //   onEdgesChange([{ type: "select", id: "e1", selected: true }])
    //   onSelectionChange({ nodes: [], edges: [{ id: "e1" }] })
    // If onSelectionChange fires AFTER onEdgesChange.select, the edge
    // selection set by the select handler gets wiped.

    // Step 1: onEdgesChange.select fires
    useSelectionStore.getState().setEdgeSelected("e1", true);
    expect(useSelectionStore.getState().edges).toEqual({ e1: true });

    // Step 2: onSelectionChange fires, calls replaceSelection([])
    // (onSelectionChange only passes node ids, ignoring the edge)
    useSelectionStore.getState().replaceSelection([]);

    // Bug: edge selection is lost!
    expect(useSelectionStore.getState().edges).toEqual({});
  });

  test("edge selection is preserved when replaceSelection accepts edge ids", () => {
    // The fix: onSelectionChange should pass edge ids too, so replaceSelection
    // preserves edge selection instead of always clearing it.

    // Step 1: onEdgesChange.select fires
    useSelectionStore.getState().setEdgeSelected("e1", true);
    expect(useSelectionStore.getState().edges).toEqual({ e1: true });

    // Step 2: onSelectionChange fires with both nodes and edges
    // (after fix, replaceSelection accepts edgeIds)
    useSelectionStore.getState().replaceSelection([], ["e1"]);

    // Edge selection is preserved
    expect(useSelectionStore.getState().edges).toEqual({ e1: true });
    expect(useSelectionStore.getState().nodes).toEqual({});
  });
});