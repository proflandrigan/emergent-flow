import type { CatalogNode } from "../catalog/types";
import { newId } from "../store/ids";
import type { CanvasModel, EdgeModel, NodeModel, ParamModel, PortModel } from "../store/model";

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

  // Group nodes in the first 3 columns as "Stage A"
  const stageANodes = Object.values(nodes).filter((n) => n.position.x < 3 * SPACING_X);
  const stageAGroupId = newId("group");
  for (const node of stageANodes) {
    nodes[node.id] = { ...node, groupId: stageAGroupId };
  }

  // Group nodes in columns 3-5 as "Stage B"
  const stageBNodes = Object.values(nodes).filter((n) => n.position.x >= 3 * SPACING_X && n.position.x < 6 * SPACING_X);
  const stageBGroupId = newId("group");
  for (const node of stageBNodes) {
    nodes[node.id] = { ...node, groupId: stageBGroupId };
  }

  // Compute group bounding boxes
  const stageAPositions = stageANodes.map((n) => n.position);
  const stageBPositions = stageBNodes.map((n) => n.position);

  const groupMeta: Record<string, { label: string; color: string; position: { x: number; y: number } }> = {
    [stageAGroupId]: {
      label: "Stage A",
      color: "#6366f1",
      position: {
        x: Math.min(...stageAPositions.map((p) => p.x)) - 16,
        y: Math.min(...stageAPositions.map((p) => p.y)) - 28,
      },
    },
    [stageBGroupId]: {
      label: "Stage B",
      color: "#ec4899",
      position: {
        x: Math.min(...stageBPositions.map((p) => p.x)) - 16,
        y: Math.min(...stageBPositions.map((p) => p.y)) - 28,
      },
    },
  };

  return { paradigm: "functional", nodes, edges: {}, groupMeta };
}
