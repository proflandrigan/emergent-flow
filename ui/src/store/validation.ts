export type Severity = "error" | "warning";

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
}

export interface Diagnostics {
  diagnostics: Diagnostic[];
  edge_compatibility: Record<string, boolean | null>;
}
