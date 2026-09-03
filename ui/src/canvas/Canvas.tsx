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
  type Edge,
  type EdgeChange,
  type EdgeTypes,
  type Node,
  type NodeChange,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import { Map, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { useCatalog } from "../catalog/useCatalog";
import type { NodeModel } from "../store/model";
import { useCollapseStore } from "../store/collapseStore";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { useLiveValidation } from "../store/useLiveValidation";
import { useValidationStore } from "../store/validationStore";
import { IconButton } from "../ui/IconButton";
import { Tooltip } from "../ui/Tooltip";
import { runGraph } from "../exec/runGraph";
import { EfEdge } from "./edges/EfEdge";
import { EfNode } from "./nodes/EfNode";
import { GroupNode } from "./nodes/GroupNode";
import { CompositeNode } from "./nodes/CompositeNode";
import { NoteNode } from "./nodes/NoteNode";
import { CalloutNode } from "./nodes/CalloutNode";
import { SnapshotNode } from "./nodes/SnapshotNode";
import { FindNodeModal } from "./FindNodeModal";
import { ProblemsPanel } from "./ProblemsPanel";
import { NodeContextMenu } from "./NodeContextMenu";
import { NodeInfoPanel } from "./NodeInfoPanel";
import { GraphOverview } from "./GraphOverview";
import { NoteAnchorOverlay } from "./NoteAnchorOverlay";
import { SelectionToolbar } from "./SelectionToolbar";
import { SubgraphBreadcrumb } from "./SubgraphBreadcrumb";
import { OverlayModal } from "../ui/OverlayModal";
import {
  applyCollapsedGroups,
  applyGroupNesting,
  reanchorEdgesForCollapsedGroups,
  toAbsolutePosition,
  toRFEdge,
  toRFNode,
} from "./toReactFlow";
import { fromIR } from "../store/ir";
import { useSubgraphStore, currentSubgraph } from "../store/subgraphStore";

const nodeTypes: NodeTypes = { efNode: EfNode, noteNode: NoteNode, groupNode: GroupNode, compositeNode: CompositeNode, snapshotNode: SnapshotNode, calloutNode: CalloutNode };
const edgeTypes: EdgeTypes = { efEdge: EfEdge };

export function Canvas(): JSX.Element {
  useLiveValidation();
  const catalog = useCatalog();

  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const moveNode = useGraphStore((s) => s.moveNode);
  const moveGroup = useGraphStore((s) => s.moveGroup);
  const endNodeDrag = useGraphStore((s) => s.endNodeDrag);
  const removeNode = useGraphStore((s) => s.removeNode);
  const removeEdge = useGraphStore((s) => s.removeEdge);
  const connect = useGraphStore((s) => s.connect);
  const pasteNodes = useGraphStore((s) => s.pasteNodes);
  const groupSelection = useGraphStore((s) => s.groupSelection);
  const ungroupSelection = useGraphStore((s) => s.ungroupSelection);
  const extractToComposite = useGraphStore((s) => s.extractToComposite);
  const addCalloutAroundSelection = useGraphStore((s) => s.addCalloutAroundSelection);

  const selNodes = useSelectionStore((s) => s.nodes);
  const selEdges = useSelectionStore((s) => s.edges);
  const setNodeSelected = useSelectionStore((s) => s.setNodeSelected);
  const setEdgeSelected = useSelectionStore((s) => s.setEdgeSelected);
  const clearSelection = useSelectionStore((s) => s.clear);
  const replaceSelection = useSelectionStore((s) => s.replaceSelection);

  const edgeCompatibility = useValidationStore((s) => s.edgeCompatibility);
  const diagnostics = useValidationStore((s) => s.diagnostics);

  const statuses = useExecutionStore((s) => s.statuses);
  const results = useExecutionStore((s) => s.results);

  const familyByType = useMemo(
    () => Object.fromEntries(catalog.nodes.map((n) => [n.type, n.family])),
    [catalog],
  );

  const descriptionByType = useMemo(
    () => Object.fromEntries(catalog.nodes.map((n) => [n.type, n.description ?? null])),
    [catalog],
  );

  const reasons = useMemo(() => {
    const m: Record<string, string> = {};
    for (const d of diagnostics) {
      if (d.edge_id) {
        m[d.edge_id] = d.message;
      }
    }
    return m;
  }, [diagnostics]);

  const collapsedMap = useCollapseStore((s) => s.collapsed);
  const collapsedGroupIds = useMemo(
    () => new Set(Object.keys(collapsedMap).filter((id) => collapsedMap[id])),
    [collapsedMap],
  );

  // Subgraph navigation: when inside a composite, render its subgraph's nodes/edges instead.
  const breadcrumbs = useSubgraphStore((s) => s.breadcrumbs);
  const pushSubgraph = useSubgraphStore((s) => s.pushSubgraph);
  const activeSubgraph = useMemo(() => currentSubgraph({ breadcrumbs }), [breadcrumbs]);
  const subgraphModel = useMemo(() => {
    if (!activeSubgraph) return null;
    return fromIR(activeSubgraph);
  }, [activeSubgraph]);
  const activeNodes = subgraphModel?.nodes ?? nodes;
  const activeEdges = subgraphModel?.edges ?? edges;
  const isInSubgraph = breadcrumbs.length > 0;

  const rfNodes = useMemo(() => {
    const nodeModels = Object.values(activeNodes);
    const base = nodeModels.map((n) =>
      toRFNode(
        n,
        !!selNodes[n.id],
        statuses[n.id]?.status,
        results[n.id],
        familyByType[n.type] ?? null,
        descriptionByType[n.type] ?? null,
      ),
    );
    const nested = applyGroupNesting(nodeModels, base);
    const collapsed = applyCollapsedGroups(nodeModels, collapsedGroupIds, nested);
    // When in a subgraph view, make all nodes non-draggable (read-only exploration).
    if (isInSubgraph) {
      return collapsed.map((n) => ({ ...n, draggable: false }));
    }
    return collapsed;
  }, [activeNodes, selNodes, statuses, results, familyByType, descriptionByType, collapsedGroupIds, isInSubgraph]);
  const rfEdges = useMemo(() => {
    const base = Object.values(activeEdges).map((e) =>
      toRFEdge(e, !!selEdges[e.id], edgeCompatibility[e.id], reasons[e.id]),
    );
    return reanchorEdgesForCollapsedGroups(Object.values(activeNodes), collapsedGroupIds, base);
  }, [activeEdges, selEdges, edgeCompatibility, reasons, activeNodes, collapsedGroupIds]);

  const selectedNodeIds = useMemo(
    () => Object.keys(selNodes).filter((id) => selNodes[id]),
    [selNodes],
  );

  const canGroup = selectedNodeIds.length > 1;
  const canUngroup = useMemo(
    () =>
      selectedNodeIds.some((id) => {
        const node = nodes[id];
        return node && (node.type === "layout.group" || !!node.groupId);
      }),
    [selectedNodeIds, nodes],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      if (isInSubgraph) {
        return; // subgraph view is read-only
      }
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          const model = nodes[change.id];
          if (model?.type === "layout.group") {
            moveGroup(change.id, change.position);
          } else {
            moveNode(change.id, toAbsolutePosition(Object.values(nodes), change.id, change.position));
          }
        } else if (change.type === "remove") {
          setNodeSelected(change.id, false);
          removeNode(change.id);
        }
      }
    },
    [isInSubgraph, moveNode, moveGroup, removeNode, setNodeSelected, nodes],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      if (isInSubgraph) {
        return; // subgraph view is read-only
      }
      for (const change of changes) {
        if (change.type === "remove") {
          setEdgeSelected(change.id, false);
          removeEdge(change.id);
        } else if (change.type === "select") {
          setEdgeSelected(change.id, change.selected);
        }
      }
    },
    [isInSubgraph, removeEdge, setEdgeSelected],
  );

  const onSelectionChange = useCallback(
    (params: { nodes: Node[]; edges: Edge[] }) => {
      if (isInSubgraph) {
        return;
      }
      replaceSelection(params.nodes.map((n) => n.id));
    },
    [isInSubgraph, replaceSelection],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (isInSubgraph) {
        return; // subgraph view is read-only
      }
      if (c.source && c.target && c.sourceHandle && c.targetHandle) {
        connect(
          { node_id: c.source, port_id: c.sourceHandle },
          { node_id: c.target, port_id: c.targetHandle },
        );
      }
    },
    [isInSubgraph, connect],
  );

  const handleMoveStart = useCallback(() => {
    document.body.classList.add("ef-panning");
  }, []);

  const handleMoveEnd = useCallback(() => {
    document.body.classList.remove("ef-panning");
  }, []);

  const handleCallout = useCallback(() => {
    if (selectedNodeIds.length < 2) return;
    addCalloutAroundSelection(selectedNodeIds);
  }, [selectedNodeIds, addCalloutAroundSelection]);

  const onNodeDragStop = useCallback(() => {
    if (isInSubgraph) {
      return;
    }
    endNodeDrag();
  }, [isInSubgraph, endNodeDrag]);

  const handleNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, rfNode: (typeof rfNodes)[number]) => {
      const model = activeNodes[rfNode.id];
      if (!model || model.type !== "layout.composite" || !model.subgraph) {
        return;
      }
      const paramValue = (name: string): unknown =>
        model.params.find((p) => p.name === name)?.value;
      const label = typeof paramValue("label") === "string" ? (paramValue("label") as string) : "Composite";
      pushSubgraph({
        compositeId: model.id,
        label,
        subgraph: model.subgraph,
      });
    },
    [activeNodes, pushSubgraph, isInSubgraph],
  );

  const [contextMenu, setContextMenu] = useState<{
    nodeId: string;
    x: number;
    y: number;
  } | null>(null);
  const [infoNodeId, setInfoNodeId] = useState<string | null>(null);
  const [clipboard, setClipboard] = useState<NodeModel[] | null>(null);
  const [findModalOpen, setFindModalOpen] = useState(false);
  const [overviewOpen, setOverviewOpen] = useState<boolean>(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const reactFlowInstance = useRef<any>(null);

  const infoCatalogNode = infoNodeId
    ? catalog.nodes.find((n) => n.type === nodes[infoNodeId]?.type)
    : undefined;

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  const onNodeContextMenu: NodeMouseHandler = useCallback((event, node) => {
    event.preventDefault();
    setContextMenu({ nodeId: node.id, x: event.clientX, y: event.clientY });
  }, []);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onInit = useCallback((instance: any) => {
    reactFlowInstance.current = instance;
  }, []);

  const navigateToNode = useCallback(
    (nodeId: string) => {
      const node = nodes[nodeId];
      if (!node || !reactFlowInstance.current) return;
      reactFlowInstance.current.setCenter(node.position.x, node.position.y, {
        zoom: 1,
        duration: 200,
      });
    },
    [nodes],
  );

  const handleOverviewNavigate = useCallback(
    (nodeId: string) => {
      navigateToNode(nodeId);
      setOverviewOpen(false);
    },
    [navigateToNode],
  );

  useEffect(() => {
    if (!contextMenu) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") closeContextMenu();
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("click", closeContextMenu);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("click", closeContextMenu);
    };
  }, [contextMenu, closeContextMenu]);

  useEffect(() => {
    function isEditableTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      return (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      );
    }

    function onKeyDown(e: KeyboardEvent) {
      if (isEditableTarget(e.target)) {
        return;
      }
      const isModifier = e.metaKey || e.ctrlKey;
      if (!isModifier) {
        return;
      }
      const key = e.key.toLowerCase();
      if (key === "c") {
        const selectedIds = Object.keys(selNodes).filter((id) => selNodes[id]);
        if (selectedIds.length === 0) {
          return;
        }
        const models = selectedIds
          .map((id) => nodes[id])
          .filter((n): n is NodeModel => Boolean(n));
        if (models.length === 0) {
          return;
        }
        setClipboard(models);
      } else if (key === "v") {
        if (!clipboard || clipboard.length === 0) {
          return;
        }
        const newIds = pasteNodes(clipboard);
        clearSelection();
        for (const id of newIds) {
          setNodeSelected(id, true);
        }
      } else if (key === "k") {
        e.preventDefault();
        setFindModalOpen(true);
      } else if (key === "0") {
        e.preventDefault();
        if (reactFlowInstance.current) {
          reactFlowInstance.current.fitView({ duration: 200 });
        }
      } else if (key === "e" && e.shiftKey) {
        e.preventDefault();
        const selectedIds = Object.keys(selNodes).filter((id) => selNodes[id]);
        if (selectedIds.length > 0 && reactFlowInstance.current) {
          reactFlowInstance.current.fitView({
            nodes: selectedIds.map((id) => ({ id })),
            duration: 200,
            padding: 0.2,
          });
        }
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [clipboard, nodes, selNodes, pasteNodes, clearSelection, setNodeSelected, setFindModalOpen]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      {isInSubgraph && (
        <div style={{ position: "absolute", top: 8, left: 8, zIndex: 20 }}>
          <SubgraphBreadcrumb />
        </div>
      )}
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onMoveStart={handleMoveStart}
        onMoveEnd={handleMoveEnd}
        onNodeDragStop={onNodeDragStop}
        onEdgesChange={onEdgesChange}
        onSelectionChange={onSelectionChange}
        onConnect={onConnect}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        onInit={onInit}
        selectionOnDrag
        multiSelectionKeyCode="Shift"
        deleteKeyCode={isInSubgraph ? [] : ["Backspace", "Delete"]}
        fitView
        onlyRenderVisibleElements
        nodesDraggable={!isInSubgraph}
        nodesConnectable={!isInSubgraph}
        elementsSelectable={!isInSubgraph}
        style={
          {
            "--xy-selection-background-color": "var(--accent-soft)",
            "--xy-selection-border": "1px dotted var(--accent)",
          } as CSSProperties
        }
      >
        <Background color="var(--grid-dot)" />
        <NoteAnchorOverlay />
        <Controls
          className="glass"
          style={
            {
              "--xy-controls-button-background-color": "transparent",
              "--xy-controls-button-background-color-hover": "var(--surface-2)",
              "--xy-controls-button-color": "var(--text-secondary)",
              "--xy-controls-button-color-hover": "var(--text-primary)",
              "--xy-controls-button-border-color": "var(--border-subtle)",
            } as CSSProperties
          }
        />
      </ReactFlow>
      {(selectedNodeIds.length > 1 || canUngroup) && (
        <SelectionToolbar
          count={selectedNodeIds.length}
          onRunSelectedOnly={() => {
            void runGraph({ runOnly: selectedNodeIds });
          }}
          onRunToSelected={() => {
            void runGraph({ runTo: selectedNodeIds });
          }}
          onGroup={canGroup ? () => groupSelection(selectedNodeIds) : undefined}
          onUngroup={canUngroup ? () => ungroupSelection(selectedNodeIds) : undefined}
          onExtractToComposite={canGroup ? () => extractToComposite(selectedNodeIds) : undefined}
          onCallout={canGroup ? handleCallout : undefined}
        />
      )}
      {contextMenu && (
        <NodeContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onRunToHere={() => {
            void runGraph({ runTo: contextMenu.nodeId });
          }}
          onRunThisNode={() => {
            void runGraph({ runOnly: contextMenu.nodeId });
          }}
          onRunFromHere={() => {
            void runGraph({ runFrom: contextMenu.nodeId });
          }}
          onNodeInfo={() => setInfoNodeId(contextMenu.nodeId)}
          onClose={closeContextMenu}
        />
      )}
      {infoCatalogNode && (
        <OverlayModal width={420} onClose={() => setInfoNodeId(null)}>
          <NodeInfoPanel node={infoCatalogNode} />
        </OverlayModal>
      )}
      {findModalOpen && (
        <FindNodeModal
          onClose={() => setFindModalOpen(false)}
          onNavigate={navigateToNode}
        />
      )}
      {overviewOpen && (
        <GraphOverview
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNavigate={handleOverviewNavigate}
          onClose={() => setOverviewOpen(false)}
        />
      )}
      <ProblemsPanel onNavigate={navigateToNode} />
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 200,
          zIndex: 5,
          display: "flex",
          gap: "var(--space-1)",
        }}
      >
        <Tooltip label="Graph overview">
          <IconButton
            aria-label="Open graph overview"
            data-testid="minimap-toggle"
            onClick={() => setOverviewOpen(true)}
            style={{
              background: "var(--surface-1)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <Map size={14} />
          </IconButton>
        </Tooltip>
        <Tooltip label="Find node (⌘K)">
          <IconButton
            aria-label="Find node"
            data-testid="find-node-toggle"
            onClick={() => setFindModalOpen(true)}
            style={{
              background: "var(--surface-1)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <Search size={14} />
          </IconButton>
        </Tooltip>
      </div>
    </div>
  );
}

export default Canvas;