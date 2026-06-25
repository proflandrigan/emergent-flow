import type { CatalogNode } from "../catalog/types";
import { newId } from "../store/ids";
import type { CanvasModel, NodeModel, ParamModel, PortModel } from "../store/model";

const COLS = 40; // grid width
const SPACING_X = 220;
const SPACING_Y = 140;

// Build a CanvasModel of `count` disconnected nodes laid out in a grid, each derived from
// `spec`. Disconnected is intentional: this exists to stress NODE RENDERING (virtualization /
// LOD), not execution, so we avoid edges + validation noise.
export function generateLargeGraph(spec: CatalogNode, count: number): CanvasModel {
  const nodes: Record<string, NodeModel> = {};
  for (let i = 0; i < count; i++) {
    const nodeId = newId("node");
    const ports: PortModel[] = spec.ports.map((p) => ({
      id: newId("port"),
      name: p.name,
      direction: p.direction,
      dataType: p.data_type ?? "any",
      cardinality: p.cardinality ?? "one",
    }));
    const params: ParamModel[] = spec.params.map((p) => ({
      name: p.name,
      typeToken: p.type_token,
      value: p.default ?? null,
      default: p.default ?? null,
    }));
    nodes[nodeId] = {
      id: nodeId,
      type: spec.type,
      label: `${spec.label} ${i}`,
      paradigm: spec.paradigm === "declarative" ? "declarative" : "functional",
      params,
      ports,
      position: { x: (i % COLS) * SPACING_X, y: Math.floor(i / COLS) * SPACING_Y },
      groupId: null,
    };
  }
  return { paradigm: "functional", nodes, edges: {} };
}
