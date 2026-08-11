import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Payload } from "../store/execution";
import { isRecommendationPayload, RecommendationsPanel } from "./RecommendationsPanel";

const recommendationsPayload: Payload = {
  kind: "table",
  columns: ["user_id", "item_id", "rank", "score"],
  dtypes: ["int64", "int64", "int64", "float64"],
  shape: [4, 4],
  head: [
    { user_id: 1, item_id: "a", rank: 2, score: 0.5 },
    { user_id: 1, item_id: "b", rank: 1, score: 0.9 },
    { user_id: 2, item_id: "c", rank: 1, score: 0.8 },
    { user_id: 2, item_id: "d", rank: 2, score: 0.4 },
  ],
  truncated: false,
};

test("isRecommendationPayload narrows a table with the expected columns", () => {
  const table: Payload = {
    kind: "table",
    columns: ["user_id", "item_id", "rank", "score"],
    dtypes: [],
    shape: [0, 4],
    head: [],
    truncated: false,
  };
  expect(isRecommendationPayload(table)).toBe(true);
});

test("isRecommendationPayload rejects payloads missing the expected columns", () => {
  const table: Payload = {
    kind: "table",
    columns: ["user_id", "item_id"],
    dtypes: [],
    shape: [0, 2],
    head: [],
    truncated: false,
  };
  expect(isRecommendationPayload(table)).toBe(false);
  expect(isRecommendationPayload({ kind: "scalar", value: 1 })).toBe(false);
});

test("groups recommendation rows by user and sorts by rank ascending", () => {
  render(<RecommendationsPanel payload={recommendationsPayload} />);

  const users = screen.getAllByTestId("recommendation-user");
  expect(users.length).toBe(2);
  expect(users[0]).toHaveTextContent("User 1");
  expect(users[1]).toHaveTextContent("User 2");

  // User 1's items sorted by rank ascending: b (rank 1) then a (rank 2).
  const user1 = users[0];
  const items = user1.querySelectorAll("li");
  expect(items.length).toBe(2);
  expect(items[0]).toHaveTextContent("b");
  expect(items[0]).toHaveTextContent("0.9");
  expect(items[1]).toHaveTextContent("a");
  expect(items[1]).toHaveTextContent("0.5");
});

test("falls back to a table for a non-recommendation table payload", () => {
  const table: Payload = {
    kind: "table",
    columns: ["name", "age"],
    dtypes: ["string", "int64"],
    shape: [1, 2],
    head: [{ name: "ada", age: 36 }],
    truncated: false,
  };
  render(<RecommendationsPanel payload={table} />);
  expect(screen.queryByTestId("recommendations-panel")).not.toBeInTheDocument();
  expect(screen.getByTestId("payload-table")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "name" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "36" })).toBeInTheDocument();
});