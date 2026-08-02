export type Severity = "error" | "warning" | "info";

export function severityColor(severity: Severity | string): string {
  switch (severity) {
    case "error":
      return "var(--danger)";
    case "warning":
      return "var(--warning)";
    case "info":
      return "var(--info)";
    default:
      return "var(--text-secondary)";
  }
}

export interface Diagnostic {
  severity: Severity;
  code: string;
  message: string;
  edge_id?: string | null;
  node_id?: string | null;
  port_id?: string | null;
  port_name?: string | null;
  expected_type?: string | null;
  actual_type?: string | null;
  source?: string | null;
  rule_id?: string | null;
  related_node_ids?: string[];
}

export interface Diagnostics {
  diagnostics: Diagnostic[];
  edge_compatibility: Record<string, boolean | null>;
}
