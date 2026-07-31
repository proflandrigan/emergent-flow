import { ChevronRight } from "lucide-react";
import type { CSSProperties } from "react";

import { useSubgraphStore } from "../store/subgraphStore";

const barStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-1)",
  padding: "0.25rem 0.75rem",
  borderRadius: "var(--radius-md)",
  background: "var(--surface-2)",
  border: "1px solid var(--border-subtle)",
  fontSize: "var(--text-xs)",
  color: "var(--text-secondary)",
};

const crumbStyle: CSSProperties = {
  cursor: "pointer",
  padding: "0.125rem 0.25rem",
  borderRadius: "var(--radius-sm)",
  border: "none",
  background: "none",
  color: "inherit",
  fontSize: "inherit",
};

const activeCrumbStyle: CSSProperties = {
  ...crumbStyle,
  fontWeight: 600,
  color: "var(--text-primary)",
  cursor: "default",
};

const separatorStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  color: "var(--text-tertiary)",
};

export function SubgraphBreadcrumb(): JSX.Element | null {
  const breadcrumbs = useSubgraphStore((s) => s.breadcrumbs);
  const popTo = useSubgraphStore((s) => s.popTo);

  if (breadcrumbs.length === 0) {
    return null;
  }

  const labels = ["Top-level", ...breadcrumbs.map((b) => b.label)];

  return (
    <div style={barStyle} data-testid="subgraph-breadcrumb">
      {labels.map((label, i) => (
        <span key={`${i}-${label}`} style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}>
          {i > 0 && (
            <span style={separatorStyle}>
              <ChevronRight size={12} />
            </span>
          )}
          <button
            type="button"
            style={i === labels.length - 1 ? activeCrumbStyle : crumbStyle}
            onClick={i < labels.length - 1 ? () => popTo(i) : undefined}
            data-testid={`breadcrumb-${i}`}
          >
            {label}
          </button>
        </span>
      ))}
    </div>
  );
}

export default SubgraphBreadcrumb;
