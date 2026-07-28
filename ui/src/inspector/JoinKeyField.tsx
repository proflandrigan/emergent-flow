import type { JSX } from "react";

import type { CatalogParam } from "../catalog/types";
import { useGraphStore } from "../store/graphStore";
import type { NodeModel, ParamModel } from "../store/model";
import { useUpstreamColumnsForPort } from "./useUpstreamColumns";

interface JoinKeyFieldProps {
  node: NodeModel;
  param: ParamModel;
  meta: CatalogParam | undefined;
  leftPort: string;
  rightPort: string;
}

export function JoinKeyField({
  node,
  param,
  meta,
  leftPort,
  rightPort,
}: JoinKeyFieldProps): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const leftColumns = useUpstreamColumnsForPort(node.id, leftPort);
  const rightColumns = useUpstreamColumnsForPort(node.id, rightPort);

  let columns: string[];
  if (param.name === "on") {
    const rightSet = new Set(rightColumns);
    columns = leftColumns.filter((c) => rightSet.has(c));
  } else if (param.name === "left_on") {
    columns = leftColumns;
  } else {
    columns = rightColumns;
  }

  const testId = `param-${param.name}`;
  const selected = new Set(Array.isArray(param.value) ? (param.value as string[]) : []);

  function toggle(col: string) {
    const next = new Set(selected);
    if (next.has(col)) {
      next.delete(col);
    } else {
      next.add(col);
    }
    setParam(node.id, param.name, [...next]);
  }

  return (
    <div style={{ marginBottom: "0.75rem" }}>
      <label style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
        {meta?.label ?? param.name}
      </label>
      {columns.length === 0 ? (
        <div data-testid={testId} style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
          Run upstream nodes to populate
        </div>
      ) : (
        <div data-testid={testId}>
          {columns.map((col) => (
            <label
              key={col}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.35rem",
                padding: "0.15rem 0",
                fontSize: "var(--text-sm)",
                cursor: "pointer",
              }}
            >
              <input type="checkbox" checked={selected.has(col)} onChange={() => toggle(col)} />
              {col}
            </label>
          ))}
        </div>
      )}
      {meta?.help ? (
        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{meta.help}</div>
      ) : null}
    </div>
  );
}
