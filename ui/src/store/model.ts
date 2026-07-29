// The internal canvas model: a clean, camelCase shape decoupled from the generated IR's
// ugly numbered aliases and snake_case fields. `ui/src/store/ir.ts` translates between this
// and the IR `Graph` 1:1.

import type { Graph as IRGraph } from "../generated/ir";

export type Paradigm = "functional" | "declarative";
export type Direction = "in" | "out";
export type Cardinality = "one" | "many";

export interface PortModel {
  id: string;
  name: string;
  direction: Direction;
  dataType: string;
  cardinality: Cardinality;
  label?: string | null;
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
  // The inner graph a composite/module node owns (ADR 0003 "Option A" nesting) -- e.g. the
  // layer chain inside an `nn.module` node, which is the whole substance of a DECLARATIVE
  // graph. The canvas does not (yet) render or edit subgraphs, but it MUST carry them
  // through untouched: `loadIR` -> `toIR` is the path taken by file import/export, session
  // join/push, and accepting an agent proposal, so dropping this field silently destroys a
  // declarative model and leaves a graph that no longer compiles.
  subgraph?: IRGraph | null;
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
