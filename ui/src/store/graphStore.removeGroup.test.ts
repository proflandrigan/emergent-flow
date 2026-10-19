import { beforeEach, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useGraphStore } from "./graphStore";

const spec = (catalog as unknown as { nodes: CatalogNode[] }).nodes.find(
  (n) => n.type === "data.load_csv",
) as CatalogNode;

beforeEach(() => {
  useGraphStore.getState().reset();
});

test("removing a layout.group node leaves no dangling member groupId", () => {
  const s = useGraphStore.getState();
  const a = s.addNodeFromSpec(spec, { x: 0, y: 0 });
  const b = s.addNodeFromSpec(spec, { x: 300, y: 0 });
  const groupId = useGraphStore.getState().groupSelection([a, b]) as string;
  useGraphStore.getState().removeNode(groupId);

  const { nodes } = useGraphStore.getState();
  expect(nodes[a].groupId).toBeNull();
  expect(nodes[b].groupId).toBeNull();
  const ir = useGraphStore.getState().toIR();
  for (const n of Object.values(ir.nodes ?? {})) {
    expect(n.group_id == null || n.group_id in (ir.nodes ?? {})).toBe(true);
  }
  // undo restores the group membership
  useGraphStore.getState().undo();
  expect(useGraphStore.getState().nodes[a].groupId).toBe(groupId);
});
