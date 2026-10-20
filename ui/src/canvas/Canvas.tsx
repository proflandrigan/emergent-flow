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
import { useTraceStore } from "../store/traceStore";
import { familyMeta } from "../theme/family";
import { useLiveValidation } from "../store/useLiveValidation";
import { useValidationStore } from "../store/validationStore";
import { Button } from "../ui/Button";
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
import { ResultCardNode } from "./nodes/ResultCardNode";
import { FindNodeModal } from "./FindNodeModal";
import { ProblemsPanel } from "./ProblemsPanel";
import { LensBar } from "./LensBar";
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
import { computeLens, computeReach, computeRoute, computeTrace, type TraceResult } from "./trace";
import type { TraceMode } from "./toReactFlow";
import "./CanvasTrace.css";
import { fromIR } from "../store/ir";
import { useSubgraphStore, currentSubgraph } from "../store/subgraphStore";

const nodeTypes: NodeTypes = { efNode: EfNode, noteNode: NoteNode, groupNode: GroupNode, compositeNode: CompositeNode, snapshotNode: SnapshotNode, calloutNode: CalloutNode, resultCardNode: ResultCardNode };
const edgeTypes: EdgeTypes = { efEdge: EfEdge };

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

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
  const createResultCardForSelection = useGraphStore((s) => s.createResultCardForSelection);

  const selNodes = useSelectionStore((s) => s.nodes);
  const selEdges = useSelectionStore((s) => s.edges);
  const setNodeSelected = useSelectionStore((s) => s.setNodeSelected);
  const setEdgeSelected = useSelectionStore((s) => s.setEdgeSelected);
  const clearSelection = useSelectionStore((s) => s.clear);
  const replaceSelection = useSelectionStore((s) => s.replaceSelection);

  const traceMode = useTraceStore((s) => s.mode);
  const traceDirection = useTraceStore((s) => s.direction);
  const routeFrom = useTraceStore((s) => s.routeFrom);
  const routeTo = useTraceStore((s) => s.routeTo);
  const routePicking = useTraceStore((s) => s.routePicking);
  const lensFamilies = useTraceStore((s) => s.families);
  const toggleFamily = useTraceStore((s) => s.toggleFamily);
  const setRoute = useTraceStore((s) => s.setRoute);
  const setReach = useTraceStore((s) => s.setReach);
  const startRoutePick = useTraceStore((s) => s.startRoutePick);
  const resetTrace = useTraceStore((s) => s.reset);

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

  const rawNodes = useMemo(() => {
    const nodeModels = Object.values(activeNodes);
    const base = nodeModels.map((n) =>
      toRFNode(
        n,
        !!selNodes[n.id],
        statuses[n.id]?.status,
        results[n.id],
        familyByType[n.type] ?? null,
        descriptionByType[n.type] ?? null,
        "none" as TraceMode,
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
  const rawEdges = useMemo(() => {
    const base = Object.values(activeEdges).map((e) =>
      toRFEdge(e, !!selEdges[e.id], edgeCompatibility[e.id], reasons[e.id], "none" as TraceMode),
    );
    return reanchorEdgesForCollapsedGroups(Object.values(activeNodes), collapsedGroupIds, base);
  }, [activeEdges, selEdges, edgeCompatibility, reasons, activeNodes, collapsedGroupIds]);

  const selectedNodeIds = useMemo(
    () => Object.keys(selNodes).filter((id) => selNodes[id]),
    [selNodes],
  );

  const trace = useMemo((): TraceResult & { routeFound: boolean | null } => {
    const nodeIds = rawNodes.map((n) => n.id);
    const traceEdges = rawEdges.map((e) => ({ id: e.id, source: e.source, target: e.target }));
    switch (traceMode) {
      case "reach":
        return { ...computeReach(selectedNodeIds, nodeIds, traceEdges, traceDirection), routeFound: null };
      case "route": {
        if (!routeFrom) {
          return { ...computeTrace(selectedNodeIds, nodeIds, traceEdges), routeFound: null };
        }
        // An endpoint hidden inside a collapsed group is represented by the group node, mirroring
        // how its edges are re-anchored -- otherwise collapsing would read as "No path".
        const visibleId = (id: string): string => {
          const groupId = activeNodes[id]?.groupId;
          return groupId && collapsedGroupIds.has(groupId) ? groupId : id;
        };
        if (!routeTo) {
          // Picking a target: highlight only the origin so the user sees where the route starts.
          return { ...computeReach([visibleId(routeFrom)], nodeIds, [], "downstream"), routeFound: null };
        }
        const from = visibleId(routeFrom);
        const to = visibleId(routeTo);
        // Prefer the requested direction; fall back to the reverse so an unordered pair
        // (e.g. a two-node selection) still finds the path whichever way it runs.
        const forward = computeRoute(from, to, nodeIds, traceEdges);
        const route = forward.found ? forward : computeRoute(to, from, nodeIds, traceEdges);
        return { ...route, routeFound: route.found };
      }
      case "lens": {
        const lensNodes = rawNodes.map((n) => ({
          id: n.id,
          family: familyByType[activeNodes[n.id]?.type ?? ""] ?? null,
        }));
        return { ...computeLens(new Set(lensFamilies), lensNodes, traceEdges), routeFound: null };
      }
      default:
        return { ...computeTrace(selectedNodeIds, nodeIds, traceEdges), routeFound: null };
    }
  }, [traceMode, traceDirection, routeFrom, routeTo, lensFamilies, selectedNodeIds, rawNodes, rawEdges, familyByType, activeNodes, collapsedGroupIds]);

  const presentFamilies = useMemo(() => {
    const found = new Set<string>();
    for (const n of rawNodes) {
      const family = familyByType[activeNodes[n.id]?.type ?? ""];
      if (family) found.add(family);
    }
    // Keep active lens families listed even once their last node is gone, so the chip can still
    // be toggled off instead of leaving the whole canvas dimmed with nothing to click.
    for (const family of lensFamilies) found.add(family);
    return [...found].sort((a, b) => familyMeta(a).label.localeCompare(familyMeta(b).label));
  }, [rawNodes, activeNodes, familyByType, lensFamilies]);

  const nodeName = useCallback(
    (id: string | null): string => {
      if (!id) return "";
      const model = activeNodes[id];
      return model?.label ?? model?.type ?? id;
    },
    [activeNodes],
  );

  const rfNodes = useMemo(
    () =>
      rawNodes.map((n) => {
        const mode: TraceMode = !trace.active
          ? "none"
          : trace.highlightedNodeIds.has(n.id)
            ? "traced"
            : "dimmed";
        // efNodes carry their trace styling inline (EfNode.tsx: accent ring / dimmed opacity)
        // so the ring can outrank status styling and dimming can min with the skipped opacity.
        // Only non-efNode types (group/composite/note/callout/snapshot) get the CSS classes --
        // applying both would double-dim efNodes (wrapper opacity x inline opacity) and draw a
        // doubled accent ring.
        const isEfNode = n.type === "efNode";
        return {
          ...n,
          className:
            !isEfNode && mode === "traced"
              ? "ef-trace-traced"
              : !isEfNode && mode === "dimmed"
                ? "ef-trace-dimmed"
                : undefined,
          data: isEfNode ? { ...n.data, trace: mode } : n.data,
        };
      }),
    [rawNodes, trace],
  );

  const rfEdges = useMemo(
    () =>
      rawEdges.map((e) => {
        const mode: TraceMode = !trace.active
          ? "none"
          : trace.highlightedEdgeIds.has(e.id)
            ? "traced"
            : "dimmed";
        return { ...e, data: { ...e.data, trace: mode } };
      }),
    [rawEdges, trace],
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
        }
      }
    },
    [isInSubgraph, removeEdge, setEdgeSelected],
  );

  const onSelectionChange = useCallback(
    (params: { nodes: Node[]; edges: Edge[] }) => {
      replaceSelection(
        params.nodes.map((n) => n.id),
        params.edges.length > 0 ? params.edges.map((e) => e.id) : undefined,
      );
    },
    [replaceSelection],
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

  const handleSummarize = useCallback(() => {
    if (selectedNodeIds.length < 1) return;
    createResultCardForSelection(selectedNodeIds);
  }, [selectedNodeIds, createResultCardForSelection]);

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

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      if (routePicking && routeFrom && node.id !== routeFrom) {
        setRoute(routeFrom, node.id);
      }
    },
    [routePicking, routeFrom, setRoute],
  );

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
    if (traceMode === "selection-downstream") return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (isEditableTarget(e.target)) return;
      resetTrace();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [traceMode, resetTrace]);

  // Trace shortcuts (issue #167): U = upstream reach, D = downstream reach, R = route (one node selected:
  // pick the target by clicking; two selected: show the route between them). Plain keys only, never in inputs.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;
      const key = e.key.toLowerCase();
      if (key === "u" && selectedNodeIds.length > 0) {
        setReach("upstream");
      } else if (key === "d" && selectedNodeIds.length > 0) {
        setReach("downstream");
      } else if (key === "r" && selectedNodeIds.length === 1) {
        startRoutePick(selectedNodeIds[0]);
      } else if (key === "r" && selectedNodeIds.length === 2) {
        setRoute(selectedNodeIds[0], selectedNodeIds[1]);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [selectedNodeIds, setReach, startRoutePick, setRoute]);

  // Reach roots are the selection: once it is cleared, drop the sticky mode so the next click
  // goes back to the default downstream trace instead of silently tracing upstream.
  useEffect(() => {
    if (traceMode === "reach" && selectedNodeIds.length === 0) resetTrace();
  }, [traceMode, selectedNodeIds, resetTrace]);

  // A route endpoint deleted while the route is shown would otherwise read "No path" for a ghost id.
  useEffect(() => {
    if (traceMode !== "route") return;
    if ((routeFrom && !activeNodes[routeFrom]) || (routeTo && !activeNodes[routeTo])) resetTrace();
  }, [traceMode, routeFrom, routeTo, activeNodes, resetTrace]);

  // Node ids from the previous view must not keep highlighting after subgraph navigation.
  useEffect(() => {
    resetTrace();
  }, [breadcrumbs, resetTrace]);

  const traceBanner = useMemo((): string | null => {
    if (traceMode === "reach") {
      return trace.active
        ? `Tracing ${traceDirection === "both" ? "upstream + downstream" : traceDirection} reach`
        : null;
    }
    if (traceMode === "route") {
      if (routePicking) return `Click a node to route from ${nodeName(routeFrom)}`;
      if (trace.routeFound === true) {
        return `Route between ${nodeName(routeFrom)} and ${nodeName(routeTo)}`;
      }
      if (trace.routeFound === false) {
        return `No path between ${nodeName(routeFrom)} and ${nodeName(routeTo)}`;
      }
      return null;
    }
    if (traceMode === "lens") return `Lens: ${lensFamilies.map((f) => familyMeta(f).label).join(", ")}`;
    return null;
  }, [traceMode, trace, traceDirection, routePicking, routeFrom, routeTo, lensFamilies, nodeName]);

  useEffect(() => {
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
        onNodeClick={onNodeClick}
        onInit={onInit}
        selectionOnDrag
        multiSelectionKeyCode="Shift"
        deleteKeyCode={isInSubgraph ? [] : ["Backspace", "Delete"]}
        fitView
        onlyRenderVisibleElements
        nodesDraggable={!isInSubgraph}
        nodesConnectable={!isInSubgraph}
        elementsSelectable
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
      {traceBanner && (
        <div
          data-testid="trace-banner"
          data-route-empty={trace.routeFound === false ? "true" : undefined}
          role="status"
          style={{
            position: "absolute", top: 10, left: "50%", transform: "translateX(-50%)", zIndex: 10,
            display: "inline-flex", alignItems: "center", gap: "var(--space-2)",
            padding: "var(--space-1) var(--space-3)", borderRadius: "var(--radius-md)",
            background: "var(--surface-2)", border: "1px solid var(--border-subtle)",
            fontSize: "var(--text-sm)", color: "var(--text-secondary)",
          }}
        >
          <span>{traceBanner}</span>
          <Button variant="ghost" data-testid="trace-banner-clear" onClick={resetTrace}>Clear (Esc)</Button>
        </div>
      )}
      {!isInSubgraph && (selectedNodeIds.length > 1 || canUngroup) && (
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
          onSummarize={selectedNodeIds.length >= 1 ? handleSummarize : undefined}
          onShowRoute={
            selectedNodeIds.length === 2
              ? () => setRoute(selectedNodeIds[0], selectedNodeIds[1])
              : undefined
          }
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
          onTraceUpstream={() => {
            replaceSelection([contextMenu.nodeId]);
            setReach("upstream");
          }}
          onTraceDownstream={() => {
            replaceSelection([contextMenu.nodeId]);
            setReach("downstream");
          }}
          onTraceBoth={() => {
            replaceSelection([contextMenu.nodeId]);
            setReach("both");
          }}
          onRouteFromHere={() => startRoutePick(contextMenu.nodeId)}
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
      <LensBar families={presentFamilies} active={lensFamilies} onToggle={toggleFamily} />
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