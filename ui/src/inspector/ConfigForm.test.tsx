import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import catalogJson from "../generated/catalog.json";
import type { Catalog, CatalogNode } from "../catalog/types";
import { useGraphStore } from "../store/graphStore";
import { ConfigForm } from "./ConfigForm";

// ConfigForm resolves param metadata (choices, required, help) from the live catalog via
// useCatalog(), NOT from the stored node (addNodeFromSpec keeps only param values). In jsdom
// fetch is unmocked, so useCatalog falls back synchronously to this committed catalog -- so the
// tests must use REAL catalog node types for the metadata join to resolve.
const catalog = catalogJson as unknown as Catalog;

function spec(type: string): CatalogNode {
  const found = catalog.nodes.find((n) => n.type === type);
  if (!found) {
    throw new Error(`catalog node not found: ${type}`);
  }
  return found;
}

function addNode(type: string): string {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec(type), { x: 0, y: 0 });
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);
  return id;
}

beforeEach(() => {
  useGraphStore.getState().reset();
});

test("renders a select widget with its choices", () => {
  addNode("clean.impute_missing");
  const select = screen.getByTestId("param-strategy") as HTMLSelectElement;
  const options = Array.from(select.querySelectorAll("option")).map(
    (o) => o.value,
  );
  expect(options).toEqual(["", "mean", "median", "most_frequent"]);
  expect(select.value).toBe("mean");
});

test("typing in a number input updates the store", () => {
  const id = addNode("ml.train_classifier");
  const input = screen.getByTestId("param-random_state") as HTMLInputElement;

  fireEvent.change(input, { target: { value: "5" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "random_state");
  expect(param?.value).toBe(5);
});

test("typing in a text input updates the store", () => {
  const id = addNode("data.load_csv");
  const input = screen.getByTestId("param-encoding");

  fireEvent.change(input, { target: { value: "latin-1" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "encoding");
  expect(param?.value).toBe("latin-1");
});

test("a required-but-empty param shows its error message", () => {
  // data.load_csv's `path` is required with a null default -> empty -> "Required".
  addNode("data.load_csv");
  expect(screen.getByTestId("error-path")).toHaveTextContent("Required");
});

test("renders the no-params message when the node has no params", () => {
  addNode("nn.module");
  expect(screen.getByTestId("config-no-params")).toBeInTheDocument();
});
