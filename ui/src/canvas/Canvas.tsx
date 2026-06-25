// The canvas: renders the store's nodes/edges via React Flow and wires pan/zoom, multi-select,
// drag-to-create-edge, and delete back into the store's actions. The store is the single source
// of truth for IR data (ADR 0014 Decision 3) -- React Flow's nodes/edges are DERIVED from it on
// every render via `toReactFlow.ts`. Selection is ephemeral UI state and is kept OUT of the
// store/IR.

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import { useCallback, useMemo } from "react";

import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { CmNode } from "./nodes/CmNode";
import { toRFEdge, toRFNode } from "./toReactFlow";

const nodeTypes: NodeTypes = { cmNode: CmNode };

export function Canvas(): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const moveNode = useGraphStore((s) => s.moveNode);
  const endNodeDrag = useGraphStore((s) => s.endNodeDrag);
  const removeNode = useGraphStore((s) => s.removeNode);
  const removeEdge = useGraphStore((s) => s.removeEdge);
  const connect = useGraphStore((s) => s.connect);

  const selNodes = useSelectionStore((s) => s.nodes);
  const selEdges = useSelectionStore((s) => s.edges);
  const setNodeSelected = useSelectionStore((s) => s.setNodeSelected);
  const setEdgeSelected = useSelectionStore((s) => s.setEdgeSelected);

  const rfNodes = useMemo(
    () => Object.values(nodes).map((n) => toRFNode(n, !!selNodes[n.id])),
    [nodes, selNodes],
  );
  const rfEdges = useMemo(
    () => Object.values(edges).map((e) => toRFEdge(e, !!selEdges[e.id])),
    [edges, selEdges],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          moveNode(change.id, change.position);
        } else if (change.type === "remove") {
          // Clear any lingering selection flag so a deleted node can't masquerade as a second
          // selection and make selectedNodeId() report "multiple selected".
          setNodeSelected(change.id, false);
          removeNode(change.id);
        } else if (change.type === "select") {
          setNodeSelected(change.id, change.selected);
        }
      }
    },
    [moveNode, removeNode, setNodeSelected],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes) {
        if (change.type === "remove") {
          setEdgeSelected(change.id, false);
          removeEdge(change.id);
        } else if (change.type === "select") {
          setEdgeSelected(change.id, change.selected);
        }
      }
    },
    [removeEdge, setEdgeSelected],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source && c.target && c.sourceHandle && c.targetHandle) {
        connect(
          { node_id: c.source, port_id: c.sourceHandle },
          { node_id: c.target, port_id: c.targetHandle },
        );
      }
    },
    [connect],
  );

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStop={endNodeDrag}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        selectionOnDrag
        multiSelectionKeyCode="Shift"
        deleteKeyCode={["Backspace", "Delete"]}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export default Canvas;
