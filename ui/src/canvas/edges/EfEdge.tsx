// Custom React Flow edge renderer for Emergent Flow canvas edges. Purely presentational: it draws
// the default bezier path, but colours it red when the last `/validate` verdict marked it
// incompatible, and surfaces the diagnostic message as a native hover tooltip via SVG `<title>`.
// The edge is ALWAYS drawn -- this component only colours an existing connection, it never
// decides whether one is allowed (the store is the single source of truth for IR data).

import { useState } from "react";
import {
  BaseEdge,
  getBezierPath,
  useNodesData,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { familyMeta } from "../../theme/family";
import type { EfNodeData } from "../nodes/EfNode";
import type { TraceMode } from "../toReactFlow";

// React Flow v12 constrains edge `data` to `Record<string, unknown>`, so the data interface
// must carry an index signature; extending Record satisfies that without weakening the named
// fields (the index's `unknown` value type accepts anything).
export interface EfEdgeData extends Record<string, unknown> {
  incompatible?: boolean;
  reason?: string | null;
  trace?: TraceMode;
}

type EfEdgeType = Edge<EfEdgeData, "efEdge">;

export function EfEdge(props: EdgeProps<EfEdgeType>): JSX.Element {
  const {
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  } = props;

  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const [hovered, setHovered] = useState(false);

  const sourceNode = useNodesData(props.source);
  const sourceFamily = (sourceNode?.data as EfNodeData | undefined)?.family ?? undefined;
  const meta = familyMeta(sourceFamily ?? "");

  const incompatible = props.data?.incompatible ?? false;
  const traceMode = props.data?.trace;
  const strokeColor = traceMode === "traced"
    ? "var(--accent)"
    : traceMode === "dimmed"
      ? "var(--border-subtle)"
      : incompatible
        ? "var(--danger)"
        : props.selected || hovered
          ? meta.color
          : "var(--border-strong)";
  const strokeWidth = traceMode === "traced" ? 2.5 : traceMode === "dimmed" ? 1 : incompatible ? 2 : 1.5;
  const style = {
    ...props.style,
    stroke: strokeColor,
    strokeWidth,
    ...(traceMode === "dimmed" ? { opacity: 0.4 } : {}),
  };

  return (
    <g onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      {incompatible && props.data?.reason ? <title>{props.data.reason}</title> : null}
      <BaseEdge id={props.id} path={edgePath} style={style} markerEnd={props.markerEnd} />
    </g>
  );
}

export default EfEdge;
