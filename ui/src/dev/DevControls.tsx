import catalog from "../generated/catalog.json";
import type { CatalogNode } from "../catalog/types";
import { generateLargeGraph } from "./generateLargeGraph";
import { useGraphStore } from "../store/graphStore";

export function DevControls(): JSX.Element | null {
  if (!import.meta.env.DEV) return null;

  const spec = (catalog as unknown as { nodes: CatalogNode[] }).nodes[0];

  if (!spec) {
    return null;
  }

  return (
    <button
      type="button"
      data-testid="dev-load-large"
      onClick={() => {
        useGraphStore.getState().loadModel(generateLargeGraph(spec, 1000));
      }}
    >
      Load 1000 nodes
    </button>
  );
}
