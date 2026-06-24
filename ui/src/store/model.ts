// The internal canvas model: a clean, camelCase shape decoupled from the generated IR's
// ugly numbered aliases and snake_case fields. `ui/src/store/ir.ts` translates between this
// and the IR `Graph` 1:1.

export type Paradigm = "functional" | "declarative";
export type Direction = "in" | "out";
export type Cardinality = "one" | "many";

export interface PortModel {
  id: string;
  name: string;
  direction: Direction;
  dataType: string;
  cardinality: Cardinality;
}

export interface ParamModel {
  name: string;
  typeToken: string;
  value: unknown;
  default?: unknown;
}

export interface NodeModel {
  id: string;
  type: string;
  label?: string;
  paradigm: Paradigm;
  params: ParamModel[];
  ports: PortModel[];
  position: { x: number; y: number };
  groupId?: string | null;
}

export interface EdgeModel {
  id: string;
  source: { node_id: string; port_id: string };
  target: { node_id: string; port_id: string };
}

export interface CanvasModel {
  schemaVersion?: number;
  name?: string;
  paradigm: Paradigm;
  nodes: Record<string, NodeModel>;
  edges: Record<string, EdgeModel>;
}
