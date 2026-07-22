// The canonical client state container (ADR 0014 Decision 3): a single Zustand store holding
// the canvas model `{ nodes, edges, params }` plus the actions the canvas (React Flow, palette,
// undo/redo) drives. Serialization to/from the wire IR goes through the pure mappers in
// `./ir.ts` -- this store owns *when* state changes, not *how* it maps to the IR.

import { create } from "zustand";

import type { CatalogNode } from "../catalog/types";
import type { Graph } from "../generated/ir";
import { useExecutionStore } from "./executionStore";
import { layeredLayout, separateOverlappingNodes } from "../canvas/layout";
import { newId } from "./ids";
import { fromIR, toIR } from "./ir";
import { useValidationStore } from "./validationStore";
import type {
  CanvasModel,
  EdgeModel,
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
  };
}

// Snapshot ONLY the model fields -- history must never leak into the IR (toIR builds its own
// object already) and must never carry a live reference into past/future (hence structuredClone).
const HISTORY_LIMIT = 100;

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
  connect: (
    source: { node_id: string; port_id: string },
    target: { node_id: string; port_id: string },
  ) => string | null;
  pasteNodes: (models: NodeModel[]) => string[];
  removeEdge: (edgeId: string) => void;
  toIR: () => Graph;
  loadIR: (graph: Graph) => void;
  loadModel: (model: CanvasModel) => void;
  tidyLayout: () => void;
  reset: () => void;
  pushHistory: (txn: string) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
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
      nodes: { ...state.nodes, [nodeId]: node },
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
    });
  },

  loadIR(graph) {
    get().pushHistory("loadIR");
    const model = fromIR(graph);
    set({ ...model, nodes: separateOverlappingNodes(model.nodes) });
    clearDerivedStores();
  },

  loadModel(model) {
    get().pushHistory("loadModel");
    set({
      schemaVersion: model.schemaVersion,
      name: model.name,
      paradigm: model.paradigm,
      nodes: model.nodes,
      edges: model.edges,
    });
    clearDerivedStores();
  },

  tidyLayout() {
    get().pushHistory("tidyLayout");
    set((state) => ({ nodes: layeredLayout(state.nodes, state.edges) }));
  },

  reset() {
    set({ ...emptyGraph(), past: [], future: [], _lastTxn: null });
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
}));
