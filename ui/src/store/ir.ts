// PURE mappers between the internal CanvasModel and the wire IR `Graph` (ADR 0001: the graph
// IR is the single source of truth; this module is the only place that translates to/from it).
//
// No React, no Zustand, no I/O -- `toIR`/`fromIR` must stay pure so they can be unit-tested in
// isolation and reused by the store without coupling the store's shape to the wire format.

import type { Edge, Graph, Node, Param, Port, PortRef } from "../generated/ir";
import type {
  CanvasModel,
  EdgeModel,
  NodeModel,
  ParamModel,
  PortModel,
} from "./model";

function paramToIR(param: ParamModel): Param {
  return {
    name: param.name,
    type_token: param.typeToken,
    value: param.value as Param["value"],
    default: param.default as Param["default"],
  };
}

function paramFromIR(param: Param): ParamModel {
  return {
    name: param.name,
    typeToken: param.type_token,
    value: param.value ?? null,
    default: param.default ?? null,
  };
}

function portToIR(port: PortModel): Port {
  return {
    id: port.id,
    name: port.name,
    direction: port.direction,
    data_type: port.dataType,
    cardinality: port.cardinality,
  };
}

function portFromIR(port: Port): PortModel {
  return {
    id: port.id ?? "",
    name: port.name,
    direction: port.direction,
    dataType: port.data_type ?? "any",
    cardinality: port.cardinality ?? "one",
  };
}

function nodeToIR(node: NodeModel): Node {
  return {
    id: node.id,
    type: node.type,
    label: node.label ?? null,
    paradigm: node.paradigm,
    position: { x: node.position.x, y: node.position.y },
    params: node.params.map(paramToIR),
    ports: node.ports.map(portToIR),
    group_id: node.groupId ?? null,
  };
}

function nodeFromIR(node: Node): NodeModel {
  return {
    id: node.id ?? "",
    type: node.type,
    label: node.label ?? undefined,
    paradigm: node.paradigm ?? "functional",
    params: (node.params ?? []).map(paramFromIR),
    ports: (node.ports ?? []).map(portFromIR),
    position: { x: node.position?.x ?? 0, y: node.position?.y ?? 0 },
    groupId: node.group_id ?? null,
  };
}

function edgeToIR(edge: EdgeModel): Edge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
  };
}

function edgeFromIR(edge: Edge): EdgeModel {
  return {
    id: edge.id ?? "",
    source: portRefFromIR(edge.source),
    target: portRefFromIR(edge.target),
  };
}

function portRefFromIR(ref: PortRef): { node_id: string; port_id: string } {
  return { node_id: ref.node_id, port_id: ref.port_id };
}

export function toIR(model: CanvasModel): Graph {
  const nodes: Record<string, Node> = {};
  for (const [id, node] of Object.entries(model.nodes)) {
    nodes[id] = nodeToIR(node);
  }

  const edges: Record<string, Edge> = {};
  for (const [id, edge] of Object.entries(model.edges)) {
    edges[id] = edgeToIR(edge);
  }

  const graph: Graph = {
    paradigm: model.paradigm,
    nodes,
    edges,
  };
  if (model.name !== undefined) {
    graph.name = model.name;
  }
  if (model.schemaVersion !== undefined) {
    graph.schema_version = model.schemaVersion;
  }
  return graph;
}

export function fromIR(graph: Graph): CanvasModel {
  const nodes: Record<string, NodeModel> = {};
  for (const [id, node] of Object.entries(graph.nodes ?? {})) {
    nodes[id] = nodeFromIR(node);
  }

  const edges: Record<string, EdgeModel> = {};
  for (const [id, edge] of Object.entries(graph.edges ?? {})) {
    edges[id] = edgeFromIR(edge);
  }

  const model: CanvasModel = {
    paradigm: graph.paradigm ?? "functional",
    nodes,
    edges,
  };
  if (graph.name !== undefined && graph.name !== null) {
    model.name = graph.name;
  }
  if (graph.schema_version !== undefined) {
    model.schemaVersion = graph.schema_version;
  }
  return model;
}
