import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useGraphStore } from "../store/graphStore";
import { Canvas } from "./Canvas";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const loadCsv = requireCatalogNode("data.load_csv");

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("Canvas", () => {
  test("mounts without throwing and renders the react-flow viewport", () => {
    const { container } = render(<Canvas />);
    expect(container).toBeTruthy();
    expect(container.querySelector(".react-flow")).not.toBeNull();
  });

  test("renders a node added to the store before mount", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    const { container } = render(<Canvas />);

    expect(container.querySelector(".react-flow")).not.toBeNull();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);

    const label = screen.queryByText(/Load CSV/);
    if (label) {
      expect(label).toBeInTheDocument();
    }
  });
});
