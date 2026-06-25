import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Payload } from "../store/execution";
import { PayloadView } from "./PayloadView";

test("renders a scalar number", () => {
  const payload: Payload = { kind: "scalar", value: 42 };
  render(<PayloadView payload={payload} />);
  expect(screen.getByTestId("payload-scalar")).toHaveTextContent("42");
});

test("renders a scalar null", () => {
  const payload: Payload = { kind: "scalar", value: null };
  render(<PayloadView payload={payload} />);
  expect(screen.getByTestId("payload-scalar")).toHaveTextContent("null");
});

test("renders truncated text with a truncated note", () => {
  const payload: Payload = {
    kind: "text",
    value: "hello world",
    length: 11,
    truncated: true,
  };
  render(<PayloadView payload={payload} />);
  const el = screen.getByTestId("payload-text");
  expect(el).toHaveTextContent("hello world");
  expect(el).toHaveTextContent("truncated, 11 chars");
});

test("renders a table", () => {
  const payload: Payload = {
    kind: "table",
    columns: ["a", "b"],
    dtypes: ["int64", "int64"],
    shape: [1, 2],
    head: [{ a: 1, b: 2 }],
    truncated: false,
  };
  render(<PayloadView payload={payload} />);
  expect(screen.getByTestId("payload-table")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "a" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "2" })).toBeInTheDocument();
});

test("renders a record with a nested scalar field", () => {
  const payload: Payload = {
    kind: "record",
    type: "Point",
    fields: { x: { kind: "scalar", value: 1 } },
  };
  render(<PayloadView payload={payload} />);
  const el = screen.getByTestId("payload-record");
  expect(el).toHaveTextContent("Point");
  expect(el).toHaveTextContent("x");
  expect(screen.getByTestId("payload-scalar")).toHaveTextContent("1");
});

test("renders json", () => {
  const payload: Payload = { kind: "json", value: { x: 1 } };
  render(<PayloadView payload={payload} />);
  expect(screen.getByTestId("payload-json")).toHaveTextContent('"x": 1');
});

test("renders unsupported", () => {
  const payload: Payload = {
    kind: "unsupported",
    type: "ndarray",
    repr: "array([1, 2, 3])",
  };
  render(<PayloadView payload={payload} />);
  const el = screen.getByTestId("payload-unsupported");
  expect(el).toHaveTextContent("ndarray");
  expect(el).toHaveTextContent("array([1, 2, 3])");
});
