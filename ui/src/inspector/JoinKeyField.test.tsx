import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import catalogJson from "../generated/catalog.json";
import type { Catalog, CatalogNode } from "../catalog/types";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { ConfigForm } from "./ConfigForm";

const catalog = catalogJson as unknown as Catalog;

function spec(type: string): CatalogNode {
  const found = catalog.nodes.find((n) => n.type === type);
  if (!found) {
    throw new Error(`catalog node not found: ${type}`);
  }
  return found;
}

beforeEach(() => {
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
});

test("clean.merge scopes left_on/right_on/on column suggestions to each side", () => {
  const store = useGraphStore.getState();
  const leftId = store.addNodeFromSpec(spec("data.load_csv"), { x: 0, y: 0 });
  const rightId = store.addNodeFromSpec(spec("data.load_csv"), { x: 0, y: 100 });
  const mergeId = store.addNodeFromSpec(spec("clean.merge"), { x: 200, y: 50 });

  const leftOutPort = useGraphStore
    .getState()
    .nodes[leftId].ports.find((p) => p.direction === "out")!;
  const rightOutPort = useGraphStore
    .getState()
    .nodes[rightId].ports.find((p) => p.direction === "out")!;
  const mergeNode = useGraphStore.getState().nodes[mergeId];
  const mergeLeftPort = mergeNode.ports.find((p) => p.name === "left" && p.direction === "in")!;
  const mergeRightPort = mergeNode.ports.find((p) => p.name === "right" && p.direction === "in")!;

  useGraphStore
    .getState()
    .connect(
      { node_id: leftId, port_id: leftOutPort.id },
      { node_id: mergeId, port_id: mergeLeftPort.id },
    );
  useGraphStore
    .getState()
    .connect(
      { node_id: rightId, port_id: rightOutPort.id },
      { node_id: mergeId, port_id: mergeRightPort.id },
    );

  useExecutionStore.getState().setNodeResult(leftId, {
    frame: {
      kind: "table",
      columns: ["user_id", "name"],
      dtypes: ["int64", "object"],
      shape: [3, 2],
      head: [],
      truncated: false,
    },
  });
  useExecutionStore.getState().setNodeResult(rightId, {
    frame: {
      kind: "table",
      columns: ["user_id", "score"],
      dtypes: ["int64", "float64"],
      shape: [3, 2],
      head: [],
      truncated: false,
    },
  });

  const node = useGraphStore.getState().nodes[mergeId];
  render(<ConfigForm node={node} />);

  const leftOnField = screen.getByTestId("param-left_on");
  expect(leftOnField).toHaveTextContent("name");
  expect(leftOnField).not.toHaveTextContent("score");

  const rightOnField = screen.getByTestId("param-right_on");
  expect(rightOnField).toHaveTextContent("score");
  expect(rightOnField).not.toHaveTextContent("name");

  const onField = screen.getByTestId("param-on");
  expect(onField).toHaveTextContent("user_id");
  expect(onField).not.toHaveTextContent("name");
  expect(onField).not.toHaveTextContent("score");
});
