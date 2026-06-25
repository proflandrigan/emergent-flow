// Custom React Flow edge renderer for Emergent Flow canvas edges. Purely presentational: it draws
// the default bezier path, but colours it red when the last `/validate` verdict marked it
// incompatible, and surfaces the diagnostic message as a native hover tooltip via SVG `<title>`.
// The edge is ALWAYS drawn -- this component only colours an existing connection, it never
// decides whether one is allowed (the store is the single source of truth for IR data).

import {
  BaseEdge,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

// React Flow v12 constrains edge `data` to `Record<string, unknown>`, so the data interface
// must carry an index signature; extending Record satisfies that without weakening the named
// fields (the index's `unknown` value type accepts anything).
export interface EfEdgeData extends Record<string, unknown> {
  incompatible?: boolean;
  reason?: string | null;
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

  const incompatible = props.data?.incompatible ?? false;
  const style = {
    ...props.style,
    ...(incompatible ? { stroke: "#c00", strokeWidth: 2 } : {}),
  };

  return (
    <g>
      {incompatible && props.data?.reason ? <title>{props.data.reason}</title> : null}
      <BaseEdge id={props.id} path={edgePath} style={style} markerEnd={props.markerEnd} />
    </g>
  );
}

export default EfEdge;
