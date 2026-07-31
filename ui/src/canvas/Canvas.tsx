// The canvas: renders the store's nodes/edges via React Flow and wires pan/zoom, multi-select,
// drag-to-create-edge, and delete back into the store's actions. The store is the single source
// of truth for IR data (ADR 0014 Decision 3) -- React Flow's nodes/edges are DERIVED from it on
// every render via `toReactFlow.ts`. Selection is ephemeral UI state and is kept OUT of the
// store/IR.

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type EdgeTypes,
  type NodeChange,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import { Map, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { useCatalog } from "../catalog/useCatalog";
import type { NodeModel } from "../store/model";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { useLiveValidation } from "../store/useLiveValidation";
import { useValidationStore } from "../store/validationStore";
import { familyMeta } from "../theme/family";
import { IconButton } from "../ui/IconButton";
import { Tooltip } from "../ui/Tooltip";
import { runGraph } from "../exec/runGraph";
import { EfEdge } from "./edges/EfEdge";
import { EfNode } from "./nodes/EfNode";
import { NoteNode } from "./nodes/NoteNode";
import { GroupNode } from "./nodes/GroupNode";
import { FindNodeModal } from "./FindNodeModal";
import { ProblemsPanel } from "./ProblemsPanel";
import { NodeContextMenu } from "./NodeContextMenu";
import { NodeInfoPanel } from "./NodeInfoPanel";
import { NoteAnchorOverlay } from "./NoteAnchorOverlay";
import { SelectionToolbar } from "./SelectionToolbar";
import { OverlayModal } from "../ui/OverlayModal";
import { toRFEdge, toRFNode, toRFGroupNodes, type AnyRFNode } from "./toReactFlow";

const nodeTypes: NodeTypes = { efNode: EfNode, noteNode: NoteNode, groupNode: GroupNode };
const edgeTypes: EdgeTypes = { efEdge: EfEdge };

export function Canvas(): JSX.Element {
  useLiveValidation();
  const catalog = useCatalog();

  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const moveNode = useGraphStore((s) => s.moveNode);
  const endNodeDrag = useGraphStore((s) => s.endNodeDrag);
  const removeNode = useGraphStore((s) => s.removeNode);
  const removeEdge = useGraphStore((s) => s.removeEdge);
  const connect = useGraphStore((s) => s.connect);
  const pasteNodes = useGraphStore((s) => s.pasteNodes);

  const groupMeta = useGraphStore((s) => s.groupMeta);
  const groupNodes = useGraphStore((s) => s.groupNodes);
  const ungroupNodes = useGraphStore((s) => s.ungroupNodes);
  const setGroupMeta = useGraphStore((s) => s.setGroupMeta);

  const selNodes = useSelectionStore((s) => s.nodes);
  const selEdges = useSelectionStore((s) => s.edges);
  const setNodeSelected = useSelectionStore((s) => s.setNodeSelected);
  const setEdgeSelected = useSelectionStore((s) => s.setEdgeSelected);
  const clearSelection = useSelectionStore((s) => s.clear);

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

  const rfNodes: AnyRFNode[] = useMemo(
    () => {
      const nodeRFs = Object.values(nodes).map((n) =>
        toRFNode(
          n,
          !!selNodes[n.id],
          statuses[n.id]?.status,
          results[n.id],
          familyByType[n.type] ?? null,
          descriptionByType[n.type] ?? null,
          groupMeta,
          statuses,
        ),
      );
      const groupRFs = toRFGroupNodes(groupMeta, nodes, statuses);
      return [...nodeRFs, ...groupRFs];
    },
    [nodes, selNodes, statuses, results, familyByType, descriptionByType, groupMeta],
  );
  const rfEdges = useMemo(
    () =>
      Object.values(edges).map((e) =>
        toRFEdge(e, !!selEdges[e.id], edgeCompatibility[e.id], reasons[e.id]),
      ),
    [edges, selEdges, edgeCompatibility, reasons, groupMeta],
  );

  const selectedNodeIds = useMemo(
    () => Object.keys(selNodes).filter((id) => selNodes[id]),
    [selNodes],
  );

  const canUngroup = useMemo(() => {
    if (selectedNodeIds.length < 2) return false;
    const firstGroup = nodes[selectedNodeIds[0]]?.groupId;
    if (!firstGroup) return false;
    return selectedNodeIds.every((id) => nodes[id]?.groupId === firstGroup);
  }, [selectedNodeIds, nodes]);

  const suggestedGroupName = useMemo(() => {
    return `Group ${Object.keys(groupMeta ?? {}).length + 1}`;
  }, [groupMeta]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          const meta = groupMeta?.[change.id];
          if (meta) {
            // Group node dragged — update all members' absolute positions by the delta
            const dx = change.position.x - meta.position.x;
            const dy = change.position.y - meta.position.y;
            if (dx !== 0 || dy !== 0) {
              for (const [id, node] of Object.entries(nodes)) {
                if (node.groupId === change.id) {
                  moveNode(id, { x: node.position.x + dx, y: node.position.y + dy });
                }
              }
              setGroupMeta(change.id, { position: change.position });
            }
          } else {
            moveNode(change.id, change.position);
          }
        } else if (change.type === "remove") {
          setNodeSelected(change.id, false);
          removeNode(change.id);
        } else if (change.type === "select") {
          setNodeSelected(change.id, change.selected);
        }
      }
    },
    [moveNode, removeNode, setNodeSelected, groupMeta, nodes, setGroupMeta],
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

  const handleMoveStart = useCallback(() => {
    document.body.classList.add("ef-panning");
  }, []);

  const handleMoveEnd = useCallback(() => {
    document.body.classList.remove("ef-panning");
  }, []);

  const [contextMenu, setContextMenu] = useState<{
    nodeId: string;
    x: number;
    y: number;
  } | null>(null);
  const [infoNodeId, setInfoNodeId] = useState<string | null>(null);
  const [clipboard, setClipboard] = useState<NodeModel[] | null>(null);
  const [findModalOpen, setFindModalOpen] = useState(false);
  const [minimapCollapsed, setMinimapCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("ef-minimap-collapsed") === "true";
    } catch {
      return false;
    }
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const reactFlowInstance = useRef<any>(null);

  useEffect(() => {
    try {
      localStorage.setItem("ef-minimap-collapsed", String(minimapCollapsed));
    } catch {
      // ignore write errors
    }
  }, [minimapCollapsed]);

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
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onMoveStart={handleMoveStart}
        onMoveEnd={handleMoveEnd}
        onNodeDragStop={endNodeDrag}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeContextMenu={onNodeContextMenu}
        onInit={onInit}
        selectionOnDrag
        multiSelectionKeyCode="Shift"
        deleteKeyCode={["Backspace", "Delete"]}
        fitView
        onlyRenderVisibleElements
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
        {!minimapCollapsed && (
          <MiniMap
            className="glass"
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            nodeColor={(node: any) => {
              const family = node.data?.family as string | undefined;
              if (family) return familyMeta(family).color;
              return "var(--text-tertiary)";
            }}
            nodeStrokeColor="var(--border-strong)"
            maskColor="var(--glass-fill)"
            style={{
              width: 180,
              height: 140,
              bottom: 10,
              left: 10,
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
            }}
            pannable
            zoomable
          />
        )}
      </ReactFlow>
      {selectedNodeIds.length > 1 && (
        <SelectionToolbar
          count={selectedNodeIds.length}
          onRunSelectedOnly={() => {
            void runGraph({ runOnly: selectedNodeIds });
          }}
          onRunToSelected={() => {
            void runGraph({ runTo: selectedNodeIds });
          }}
          onGroup={() => {
            groupNodes(selectedNodeIds, suggestedGroupName);
          }}
          onUngroup={() => {
            const gid = nodes[selectedNodeIds[0]]?.groupId;
            if (gid) ungroupNodes(gid);
          }}
          canUngroup={canUngroup}
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
      <ProblemsPanel onNavigate={navigateToNode} />
      <div
        style={{
          position: "absolute",
          bottom: 10,
          left: 10,
          zIndex: 5,
          display: "flex",
          gap: "var(--space-1)",
        }}
      >
        <Tooltip label={minimapCollapsed ? "Show minimap" : "Hide minimap"}>
          <IconButton
            aria-label={minimapCollapsed ? "Show minimap" : "Hide minimap"}
            data-testid="minimap-toggle"
            onClick={() => setMinimapCollapsed((c) => !c)}
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
