// The canonical client state container (ADR 0014 Decision 3): a single Zustand store holding
// the canvas model `{ nodes, edges, params }` plus the actions the canvas (React Flow, palette,
// undo/redo) drives. Serialization to/from the wire IR goes through the pure mappers in
// `./ir.ts` -- this store owns *when* state changes, not *how* it maps to the IR.

import { create } from "zustand";

import type { CatalogNode } from "../catalog/types";
import type { Graph } from "../generated/ir";
import { useExecutionStore } from "./executionStore";
import { layeredLayout, separateOverlappingNodes } from "../canvas/layout";
import { computeGroupBounds, NODE_FOOTPRINT_WIDTH, NODE_FOOTPRINT_HEIGHT, GROUP_PADDING } from "../canvas/toReactFlow";
import { newId } from "./ids";
import { edgeToIR, fromIR, nodeToIR, toIR } from "./ir";
import { useValidationStore } from "./validationStore";
import type {
  CanvasModel,
  EdgeModel,
  GroupMeta,
  NodeModel,
  ParamModel,
  PortModel,
} from "./model";

// Replacing the whole graph (import / dev-load) invalidates any prior /execute and /validate
// verdicts: those are keyed by node/edge id, and ids are PRESERVED across export -> re-import,
// so without this a graph re-imported after a run would show stale results, node-status colours,
// and red edges against the freshly loaded graph. Validation re-runs automatically via
// useLiveValidation; clearing here just avoids the stale window. Execution has no live re-run,
// so clearing is the only thing that drops its now-orphaned results.
function clearDerivedStores(): void {
  useExecutionStore.getState().clear();
  useValidationStore.getState().clear();
}

function emptyGraph(): CanvasModel {
  return {
    paradigm: "functional",
    nodes: {},
    edges: {},
    groupMeta: {},
  };
}

// Snapshot ONLY the model fields -- history must never leak into the IR (toIR builds its own
// object already) and must never carry a live reference into past/future (hence structuredClone).
const HISTORY_LIMIT = 100;
const GROUP_COLORS = ["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#3b82f6", "#a855f7"];

// Fixed offset so pasted nodes are visibly distinct from their originals
// rather than landing exactly on top of them.
const PASTE_OFFSET = 40;

// Exported so callers outside this store (e.g. ProposalPanel's "edit into own" flow) can build
// a CanvasModel-shaped snapshot of the live store without re-listing its fields themselves.
export function snapshot(s: CanvasModel): CanvasModel {
  return structuredClone({
    schemaVersion: s.schemaVersion,
    name: s.name,
    paradigm: s.paradigm,
    nodes: s.nodes,
    edges: s.edges,
    groupMeta: s.groupMeta ?? {},
    params: s.params,
  });
}

export interface GraphStore extends CanvasModel {
  past: CanvasModel[];
  future: CanvasModel[];
  _lastTxn: string | null;
  addNodeFromSpec: (
    spec: CatalogNode,
    position: { x: number; y: number },
  ) => string;
  removeNode: (nodeId: string) => void;
  moveNode: (nodeId: string, position: { x: number; y: number }) => void;
  endNodeDrag: () => void;
  setParam: (nodeId: string, paramName: string, value: unknown) => void;
  setParamRef: (nodeId: string, paramName: string, ref: string | null | undefined) => void;
  connect: (
    source: { node_id: string; port_id: string },
    target: { node_id: string; port_id: string },
  ) => string | null;
  pasteNodes: (models: NodeModel[]) => string[];
  groupSelection: (nodeIds: string[]) => string | null;
  addCalloutAroundSelection: (nodeIds: string[]) => string | null;
  ungroupSelection: (nodeIds: string[]) => void;
  moveGroup: (groupId: string, position: { x: number; y: number }) => void;
  extractToComposite: (nodeIds: string[]) => string | null;
  removeEdge: (edgeId: string) => void;
  toIR: () => Graph;
  loadIR: (graph: Graph, options?: { reflow?: boolean }) => void;
  loadModel: (model: CanvasModel, options?: { reflow?: boolean }) => void;
  tidyLayout: () => void;
  reset: () => void;
  pushHistory: (txn: string) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  setName: (name: string) => void;
  addGraphParam: () => void;
  setGraphParamValue: (name: string, value: unknown) => void;
  setGraphParamType: (name: string, typeToken: string) => void;
  setGraphParamDescription: (name: string, description: string) => void;
  removeGraphParam: (name: string) => void;
  groupNodes: (nodeIds: string[], groupName?: string) => string;
  ungroupNodes: (groupId: string) => void;
  setGroupMeta: (groupId: string, meta: Partial<GroupMeta>) => void;
}

export const useGraphStore = create<GraphStore>((set, get) => ({
  ...emptyGraph(),
  past: [],
  future: [],
  _lastTxn: null,

  pushHistory(txn) {
    set((state) => {
      const past = [...state.past, snapshot(state)];
      if (past.length > HISTORY_LIMIT) {
        past.shift();
      }
      return { past, future: [], _lastTxn: txn };
    });
  },

  addNodeFromSpec(spec, position) {
    get().pushHistory("addNodeFromSpec");
    const nodeId = newId("node");
    const ports: PortModel[] = spec.ports.map((port) => ({
      id: newId("port"),
      name: port.name,
      direction: port.direction,
      dataType: port.data_type ?? "any",
      cardinality: port.cardinality ?? "one",
      label: port.label ?? null,
    }));
    const params: ParamModel[] = spec.params.map((param) => ({
      name: param.name,
      typeToken: param.type_token,
      value: param.default ?? null,
      default: param.default ?? null,
    }));
    const node: NodeModel = {
      id: nodeId,
      type: spec.type,
      label: spec.label,
      paradigm: spec.paradigm === "declarative" ? "declarative" : "functional",
      params,
      ports,
      position,
      groupId: null,
    };
    set((state) => ({
      nodes: layeredLayout({ ...state.nodes, [nodeId]: node }, state.edges),
    }));
    return nodeId;
  },

  removeNode(nodeId) {
    if (!get().nodes[nodeId]) {
      return; // nothing to remove -- don't push a no-op history entry
    }
    get().pushHistory("removeNode");
    set((state) => {
      const nodes = { ...state.nodes };
      delete nodes[nodeId];
      const edges: Record<string, EdgeModel> = {};
      for (const [id, edge] of Object.entries(state.edges)) {
        if (edge.source.node_id !== nodeId && edge.target.node_id !== nodeId) {
          edges[id] = edge;
        }
      }
      return { nodes, edges };
    });
  },

  moveNode(nodeId, position) {
    if (!get().nodes[nodeId]) {
      return; // nothing to move -- don't push a no-op history entry
    }
    const txn = `move:${nodeId}`;
    if (get()._lastTxn !== txn) {
      get().pushHistory(txn); // captures pre-drag state once; coalesces the rest of the drag
    }
    set((state) => {
      const existing = state.nodes[nodeId];
      if (!existing) {
        return {};
      }
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...existing, position },
        },
      };
    });
  },

  endNodeDrag() {
    // A drag gesture finished. Clear the move-coalescing key so the NEXT drag of the same
    // node starts a fresh history entry instead of merging into this one -- otherwise two
    // separate drags of one node (with no action between) would collapse to a single undo
    // step. `_lastTxn` is only consumed by moveNode's coalescing, so clearing it is safe.
    if (get()._lastTxn !== null) {
      set({ _lastTxn: null });
    }
  },

  setParam(nodeId, paramName, value) {
    if (!get().nodes[nodeId]) {
      return; // unknown node -- don't push a no-op history entry
    }
    get().pushHistory("setParam");
    set((state) => {
      const existing = state.nodes[nodeId];
      if (!existing) {
        return {};
      }
      const params = existing.params.map((param) =>
        param.name === paramName ? { ...param, value } : param,
      );
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: { ...existing, params },
        },
      };
    });
  },

  setParamRef(nodeId, paramName, ref) {
    const existing = get().nodes[nodeId];
    if (!existing) {
      return;
    }
    get().pushHistory("setParamRef");
    set((state) => {
      const node = state.nodes[nodeId];
      if (!node) {
        return {};
      }
      return {
        nodes: {
          ...state.nodes,
          [nodeId]: {
            ...node,
            params: node.params.map((p) =>
              p.name === paramName ? { ...p, ref } : p,
            ),
          },
        },
      };
    });
  },

  connect(source, target) {
    const state = get();
    const isDuplicate = Object.values(state.edges).some(
      (edge) =>
        edge.source.node_id === source.node_id &&
        edge.source.port_id === source.port_id &&
        edge.target.node_id === target.node_id &&
        edge.target.port_id === target.port_id,
    );
    if (isDuplicate) {
      return null;
    }
    get().pushHistory("connect");
    const edgeId = newId("edge");
    const edge: EdgeModel = { id: edgeId, source, target };
    set((state) => ({
      edges: { ...state.edges, [edgeId]: edge },
      nodes: layeredLayout(state.nodes, { ...state.edges, [edgeId]: edge }),
    }));
    return edgeId;
  },

  pasteNodes(models) {
    if (models.length === 0) {
      return [];
    }
    get().pushHistory("pasteNodes");
    const cloned: NodeModel[] = models.map((original) => ({
      ...structuredClone(original),
      id: newId("node"),
      ports: original.ports.map((port) => ({ ...port, id: newId("port") })),
      position: {
        x: original.position.x + PASTE_OFFSET,
        y: original.position.y + PASTE_OFFSET,
      },
    }));
    set((state) => {
      const nodes = { ...state.nodes };
      for (const node of cloned) {
        nodes[node.id] = node;
      }
      // Repeated Ctrl+V of the same clipboard clones from the same original
      // position every time, so back-to-back pastes land exactly on top of
      // each other -- de-overlap against the whole graph (not just this
      // paste's own clones) the same way loadIR does.
      return { nodes: separateOverlappingNodes(nodes) };
    });
    return cloned.map((n) => n.id);
  },

  groupSelection(nodeIds) {
    const ids = nodeIds.filter((id) => get().nodes[id]);
    if (ids.length < 2) {
      return null; // grouping requires at least two real nodes -- no-op, no history entry
    }
    get().pushHistory("groupSelection");
    const groupId = newId("node");
    const members = ids.map((id) => get().nodes[id]);
    const minX = Math.min(...members.map((n) => n.position.x));
    const minY = Math.min(...members.map((n) => n.position.y));
    const groupNode: NodeModel = {
      id: groupId,
      type: "layout.group",
      label: "Group",
      paradigm: "functional",
      params: [
        { name: "label", typeToken: "str", value: "Group", default: "Group" },
        { name: "color", typeToken: "str", value: "slate", default: "slate" },
      ],
      ports: [],
      position: { x: minX - 40, y: minY - 40 },
      groupId: null,
    };
    set((state) => {
      const nodes = { ...state.nodes, [groupId]: groupNode };
      for (const id of ids) {
        const existing = nodes[id];
        if (existing) {
          nodes[id] = { ...existing, groupId };
        }
      }
      return { nodes };
    });
    return groupId;
  },

  addCalloutAroundSelection(nodeIds) {
    const ids = nodeIds.filter((id) => get().nodes[id]);
    if (ids.length < 2) {
      return null;
    }
    get().pushHistory("addCallout");
    const state = get();
    // For group nodes, use the computed bounding box from their members
    // rather than the stale store position + hardcoded footprint.
    function effectiveBounds(n: NodeModel): { x: number; y: number; width: number; height: number } {
      if (n.type === "layout.group") {
        const groupMembers = Object.values(state.nodes).filter((m) => m.groupId === n.id);
        if (groupMembers.length > 0) {
          return computeGroupBounds(groupMembers);
        }
      }
      return {
        x: n.position.x,
        y: n.position.y,
        width: NODE_FOOTPRINT_WIDTH,
        height: NODE_FOOTPRINT_HEIGHT,
      };
    }
    const bounds = ids.map((id) => effectiveBounds(state.nodes[id]));
    const minX = Math.min(...bounds.map((b) => b.x));
    const minY = Math.min(...bounds.map((b) => b.y));
    const maxX = Math.max(...bounds.map((b) => b.x + b.width));
    const maxY = Math.max(...bounds.map((b) => b.y + b.height));
    const PADDING = GROUP_PADDING;
    const calloutId = newId("node");
    const calloutNode: NodeModel = {
      id: calloutId,
      type: "layout.callout",
      label: "Callout",
      paradigm: "functional",
      params: [
        { name: "label", typeToken: "str", value: "Callout", default: "Callout" },
        { name: "color", typeToken: "str", value: "blue", default: "blue" },
        { name: "width", typeToken: "int", value: Math.max(400, maxX - minX + PADDING * 2), default: 400 },
        { name: "height", typeToken: "int", value: Math.max(300, maxY - minY + PADDING * 2), default: 300 },
      ],
      ports: [],
      position: { x: minX - PADDING, y: minY - PADDING },
      groupId: null,
    };
    set((state) => ({
      nodes: { ...state.nodes, [calloutId]: calloutNode },
    }));
    return calloutId;
  },

  ungroupSelection(nodeIds) {
    const state = get();
    const groupIds = new Set<string>();
    for (const id of nodeIds) {
      const node = state.nodes[id];
      if (!node) {
        continue;
      }
      if (node.type === "layout.group") {
        groupIds.add(node.id);
      } else if (node.groupId) {
        groupIds.add(node.groupId);
      }
    }
    if (groupIds.size === 0) {
      return; // nothing to ungroup -- no-op, no history entry
    }
    get().pushHistory("ungroupSelection");
    set((state) => {
      const nodes = { ...state.nodes };
      for (const [id, node] of Object.entries(nodes)) {
        if (node.groupId && groupIds.has(node.groupId)) {
          nodes[id] = { ...node, groupId: null };
        }
      }
      for (const gid of groupIds) {
        delete nodes[gid];
      }
      return { nodes };
    });
  },

  moveGroup(groupId, position) {
    if (!get().nodes[groupId]) {
      return; // unknown group -- don't push a no-op history entry
    }
    const txn = `move-group:${groupId}`;
    if (get()._lastTxn !== txn) {
      get().pushHistory(txn); // captures pre-drag state once; coalesces the rest of the drag
    }
    set((state) => {
      const members = Object.values(state.nodes).filter((n) => n.groupId === groupId);
      const nodes = { ...state.nodes };
      if (members.length === 0) {
        nodes[groupId] = { ...state.nodes[groupId], position };
        return { nodes, _lastTxn: txn };
      }
      const bounds = computeGroupBounds(members);
      const dx = position.x - bounds.x;
      const dy = position.y - bounds.y;
      for (const member of members) {
        nodes[member.id] = {
          ...member,
          position: { x: member.position.x + dx, y: member.position.y + dy },
        };
      }
      nodes[groupId] = { ...state.nodes[groupId], position };
      return { nodes, _lastTxn: txn };
    });
  },

  extractToComposite(nodeIds) {
    const ids = nodeIds.filter((id) => get().nodes[id]);
    if (ids.length < 2) {
      return null; // extraction requires at least two real nodes -- no-op, no history entry
    }
    const idSet = new Set(ids);
    const state = get();

    // Partition edges: both endpoints inside the selection -> becomes a subgraph edge;
    // exactly one endpoint inside -> crosses the boundary and gets rewired below.
    const internalEdges: EdgeModel[] = [];
    const crossingEdges: EdgeModel[] = [];
    for (const edge of Object.values(state.edges)) {
      const sourceIn = idSet.has(edge.source.node_id);
      const targetIn = idSet.has(edge.target.node_id);
      if (sourceIn && targetIn) {
        internalEdges.push(edge);
      } else if (sourceIn || targetIn) {
        crossingEdges.push(edge);
      }
    }

    // A dangling IN port (no internal source) or exposed OUT port (no internal consumer) is
    // determined purely by the INTERNAL edge set -- a port fed/consumed only by a crossing
    // edge becomes dangling/exposed once that edge is excluded from the subgraph, exactly
    // mirroring the Python side's `resolve_composite_boundary`.
    const boundTargets = new Set(
      internalEdges.map((e) => `${e.target.node_id}:${e.target.port_id}`),
    );
    const consumedSources = new Set(
      internalEdges.map((e) => `${e.source.node_id}:${e.source.port_id}`),
    );

    // Canonical order: selected node ids sorted ascending, each node's ports in declared
    // order -- MUST match resolve_composite_boundary's ordering exactly (position i on each
    // side must refer to the same underlying port).
    const sortedIds = [...ids].sort();
    const danglingIn: { nodeId: string; portId: string }[] = [];
    const exposedOut: { nodeId: string; portId: string }[] = [];
    for (const nodeId of sortedIds) {
      const node = state.nodes[nodeId];
      for (const port of node.ports) {
        const key = `${nodeId}:${port.id}`;
        if (port.direction === "in") {
          if (!boundTargets.has(key)) {
            danglingIn.push({ nodeId, portId: port.id });
          }
        } else if (!consumedSources.has(key)) {
          exposedOut.push({ nodeId, portId: port.id });
        }
      }
    }

    get().pushHistory("extractToComposite");

    const compositeId = newId("node");
    const inPortIds = danglingIn.map(() => newId("port"));
    const outPortIds = exposedOut.map(() => newId("port"));
    // (memberNodeId:memberPortId) -> the new composite port id that boundary position maps to.
    const boundaryInByMember = new Map(
      danglingIn.map((ref, i) => [`${ref.nodeId}:${ref.portId}`, inPortIds[i]]),
    );
    const boundaryOutByMember = new Map(
      exposedOut.map((ref, i) => [`${ref.nodeId}:${ref.portId}`, outPortIds[i]]),
    );

    const subgraphNodes: Record<string, ReturnType<typeof nodeToIR>> = {};
    for (const nodeId of ids) {
      // group_id is cleared: a group membership referencing a node OUTSIDE this new subgraph
      // would violate the IR's "group_id must reference a node in the same graph" invariant.
      const member = { ...state.nodes[nodeId], groupId: null };
      subgraphNodes[nodeId] = nodeToIR(member);
    }
    const subgraphEdges: Record<string, ReturnType<typeof edgeToIR>> = {};
    for (const edge of internalEdges) {
      subgraphEdges[edge.id] = edgeToIR(edge);
    }

    const members = ids.map((id) => state.nodes[id]);
    const minX = Math.min(...members.map((n) => n.position.x));
    const minY = Math.min(...members.map((n) => n.position.y));

    function portFor(ref: { nodeId: string; portId: string }) {
      return state.nodes[ref.nodeId].ports.find((p) => p.id === ref.portId)!;
    }

    const compositeNode: NodeModel = {
      id: compositeId,
      type: "layout.composite",
      label: "Composite",
      paradigm: "functional",
      params: [{ name: "label", typeToken: "str", value: "Composite", default: "Composite" }],
      ports: [
        ...danglingIn.map((ref, i) => {
          const original = portFor(ref);
          return {
            id: inPortIds[i],
            name: `in${i}`,
            direction: "in" as const,
            dataType: original.dataType,
            cardinality: original.cardinality,
            label: null,
          };
        }),
        ...exposedOut.map((ref, i) => {
          const original = portFor(ref);
          return {
            id: outPortIds[i],
            name: `out${i}`,
            direction: "out" as const,
            dataType: original.dataType,
            cardinality: original.cardinality,
            label: null,
          };
        }),
      ],
      position: { x: minX - 40, y: minY - 40 },
      groupId: null,
      subgraph: {
        paradigm: "functional",
        nodes: subgraphNodes,
        edges: subgraphEdges,
      },
    };

    set((state) => {
      const nodes = { ...state.nodes };
      for (const id of ids) {
        delete nodes[id];
      }
      nodes[compositeId] = compositeNode;

      const edges = { ...state.edges };
      for (const edge of internalEdges) {
        delete edges[edge.id];
      }
      for (const edge of crossingEdges) {
        const sourceIn = idSet.has(edge.source.node_id);
        if (sourceIn) {
          const portId = boundaryOutByMember.get(
            `${edge.source.node_id}:${edge.source.port_id}`,
          )!;
          edges[edge.id] = { ...edge, source: { node_id: compositeId, port_id: portId } };
        } else {
          const portId = boundaryInByMember.get(
            `${edge.target.node_id}:${edge.target.port_id}`,
          )!;
          edges[edge.id] = { ...edge, target: { node_id: compositeId, port_id: portId } };
        }
      }

      return { nodes, edges };
    });

    return compositeId;
  },

  removeEdge(edgeId) {
    if (!get().edges[edgeId]) {
      return; // already gone (e.g. removeNode cleaned it up) -- don't push a no-op entry
    }
    get().pushHistory("removeEdge");
    set((state) => {
      const edges = { ...state.edges };
      delete edges[edgeId];
      return { edges };
    });
  },

  toIR() {
    const state = get();
    return toIR({
      schemaVersion: state.schemaVersion,
      name: state.name,
      paradigm: state.paradigm,
      nodes: state.nodes,
      edges: state.edges,
      params: state.params,
    });
  },

  loadIR(graph, options) {
    get().pushHistory("loadIR");
    const model = fromIR(graph);
    set({
      ...model,
      params: model.params,
      nodes: options?.reflow
        ? layeredLayout(model.nodes, model.edges)
        : separateOverlappingNodes(model.nodes),
    });
    clearDerivedStores();
  },

  loadModel(model, options) {
    get().pushHistory("loadModel");
    set({
      schemaVersion: model.schemaVersion,
      name: model.name,
      paradigm: model.paradigm,
      nodes: options?.reflow
        ? layeredLayout(model.nodes, model.edges)
        : model.nodes,
      edges: model.edges,
      groupMeta: model.groupMeta ?? {},
      params: model.params,
    });
    clearDerivedStores();
  },

  tidyLayout() {
    get().pushHistory("tidyLayout");
    set((state) => ({ nodes: layeredLayout(state.nodes, state.edges) }));
  },

  reset() {
    // `params` must be reset EXPLICITLY: zustand's set() shallow-merges, so omitting it
    // (as `emptyGraph()` does, to keep param-free graphs byte-identical) would leave stale
    // flow parameters behind across resets.
    set({
      ...emptyGraph(),
      params: undefined,
      past: [],
      future: [],
      _lastTxn: null,
    });
    clearDerivedStores();
  },

  undo() {
    const state = get();
    if (state.past.length === 0) {
      return;
    }
    const prev = state.past[state.past.length - 1];
    const past = state.past.slice(0, -1);
    const future = [...state.future, snapshot(state)];
    set({ ...prev, past, future, _lastTxn: null });
  },

  redo() {
    const state = get();
    if (state.future.length === 0) {
      return;
    }
    const next = state.future[state.future.length - 1];
    const future = state.future.slice(0, -1);
    const past = [...state.past, snapshot(state)];
    set({ ...next, past, future, _lastTxn: null });
  },

  canUndo() {
    return get().past.length > 0;
  },

  canRedo() {
    return get().future.length > 0;
  },

  setName(name) {
    get().pushHistory("setName");
    set({ name });
  },

  addGraphParam() {
    get().pushHistory("addGraphParam");
    set((state) => {
      const existing = Object.keys(state.params ?? {});
      let n = 1;
      while (existing.includes(`param${n}`)) {
        n += 1;
      }
      const name = `param${n}`;
      return {
        params: {
          ...(state.params ?? {}),
          [name]: { name, typeToken: "str", value: null, description: "" },
        },
      };
    });
  },

  setGraphParamValue(name, value) {
    const existing = get().params?.[name];
    if (!existing) {
      return;
    }
    get().pushHistory("setGraphParamValue");
    set((state) => ({
      params: { ...(state.params ?? {}), [name]: { ...existing, value } },
    }));
  },

  setGraphParamType(name, typeToken) {
    const existing = get().params?.[name];
    if (!existing) {
      return;
    }
    get().pushHistory("setGraphParamType");
    set((state) => ({
      params: { ...(state.params ?? {}), [name]: { ...existing, typeToken } },
    }));
  },

  setGraphParamDescription(name, description) {
    const existing = get().params?.[name];
    if (!existing) {
      return;
    }
    get().pushHistory("setGraphParamDescription");
    set((state) => ({
      params: { ...(state.params ?? {}), [name]: { ...existing, description } },
    }));
  },

  removeGraphParam(name) {
    if (!get().params?.[name]) {
      return;
    }
    get().pushHistory("removeGraphParam");
    set((state) => {
      const params = { ...(state.params ?? {}) };
      delete params[name];
      return { params };
    });
  },

  groupNodes(nodeIds, groupName) {
    if (nodeIds.length < 2) {
      throw new Error("groupNodes requires at least 2 nodes");
    }
    get().pushHistory("groupNodes");
    const groupId = newId("group");
    const state = get();
    const positions = nodeIds.map((id) => state.nodes[id]?.position).filter(Boolean);
    const minX = Math.min(...positions.map((p) => p.x));
    const minY = Math.min(...positions.map((p) => p.y));
    const groupMeta = {
      [groupId]: {
        label: groupName ?? `Group ${Object.keys(get().groupMeta ?? {}).length + 1}`,
        color: GROUP_COLORS[Object.keys(get().groupMeta ?? {}).length % GROUP_COLORS.length],
        position: { x: minX - 16, y: minY - 28 },
      },
    };
    set((state) => {
      const nodes = { ...state.nodes };
      const meta = { ...(state.groupMeta ?? {}), ...groupMeta };
      for (const id of nodeIds) {
        if (nodes[id]) {
          nodes[id] = { ...nodes[id], groupId };
        }
      }
      return { nodes, groupMeta: meta };
    });
    return groupId;
  },

  ungroupNodes(groupId) {
    get().pushHistory("ungroupNodes");
    set((state) => {
      const nodes: Record<string, NodeModel> = {};
      for (const [id, node] of Object.entries(state.nodes)) {
        nodes[id] = node.groupId === groupId ? { ...node, groupId: null } : node;
      }
      const meta = { ...(state.groupMeta ?? {}) };
      delete meta[groupId];
      return { nodes, groupMeta: meta };
    });
  },

  setGroupMeta(groupId, meta) {
    // Only push history for semantic changes (label, color), not position updates
    // which are tracked by the member moveNode calls during group drags.
    if (meta.label !== undefined || meta.color !== undefined) {
      get().pushHistory("setGroupMeta");
    }
    set((state) => {
      const existing = (state.groupMeta ?? {})[groupId];
      if (!existing) return {};
      return {
        groupMeta: {
          ...(state.groupMeta ?? {}),
          [groupId]: { ...existing, ...meta },
        },
      };
    });
  },
}));
