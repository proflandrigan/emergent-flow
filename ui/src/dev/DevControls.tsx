import catalog from "../generated/catalog.json";
import type { CatalogNode } from "../catalog/types";
import type { MenuItem } from "../ui/Menu";
import { generateLargeGraph } from "./generateLargeGraph";
import { useGraphStore } from "../store/graphStore";

export function getDevMenuItems(): MenuItem[] {
  if (!import.meta.env.DEV) {
    return [];
  }

  const spec = (catalog as unknown as { nodes: CatalogNode[] }).nodes[0];

  if (!spec) {
    return [];
  }

  return [
    {
      label: "Load 1000 nodes",
      testId: "dev-load-large",
      onSelect: () => {
        useGraphStore.getState().loadModel(generateLargeGraph(spec, 1000));
      },
    },
  ];
}
