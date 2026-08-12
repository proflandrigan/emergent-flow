import type {
  Edge as RFEdge,
  EdgeTypes,
  Node as RFNode,
  NodeTypes,
  ReactFlowInstance,
} from "@xyflow/react";
import { ReactFlow, ReactFlowProvider } from "@xyflow/react";
import { useEffect, useRef, type JSX } from "react";
import { OverlayModal } from "../ui/OverlayModal";

export interface GraphOverviewProps {
  nodes: RFNode[];
  edges: RFEdge[];
  nodeTypes: NodeTypes;
  edgeTypes: EdgeTypes;
  onNavigate: (nodeId: string) => void;
  onClose: () => void;
}

export function GraphOverview({
  nodes,
  edges,
  nodeTypes,
  edgeTypes,
  onNavigate,
  onClose,
}: GraphOverviewProps): JSX.Element {
  const instanceRef = useRef<ReactFlowInstance<RFNode, RFEdge> | null>(null);
  const readyRef = useRef(false);

  useEffect(() => {
    if (!readyRef.current) return;
    instanceRef.current?.fitView({ padding: 0.15, duration: 200 });
  }, [nodes.length, edges.length]);

  return (
    <OverlayModal width={860} onClose={onClose}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          deleteKeyCode={[]}
          minZoom={0.1}
          maxZoom={2.5}
          onInit={(inst) => {
            instanceRef.current = inst;
            readyRef.current = true;
          }}
          onNodeClick={(_event, node) => {
            onNavigate(node.id);
          }}
          style={{ width: "100%", height: 480 }}
        />
      </ReactFlowProvider>
    </OverlayModal>
  );
}
