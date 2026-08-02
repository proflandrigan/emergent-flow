import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { FlowParamsPanel } from "./FlowParamsPanel";

beforeEach(() => {
  useGraphStore.getState().reset();
});

test("shows the empty state when no flow parameters exist", () => {
  render(<FlowParamsPanel />);
  expect(screen.getByTestId("flow-params-empty")).toBeInTheDocument();
});

test("clicking Add parameter creates a param1 row", () => {
  render(<FlowParamsPanel />);
  fireEvent.click(screen.getByTestId("flow-params-add"));
  expect(screen.getByTestId("flow-param-param1")).toBeInTheDocument();
  expect(screen.queryByTestId("flow-params-empty")).not.toBeInTheDocument();
});

test("typing into the value input updates the store", () => {
  render(<FlowParamsPanel />);
  fireEvent.click(screen.getByTestId("flow-params-add"));
  fireEvent.change(screen.getByTestId("flow-param-value-param1"), {
    target: { value: "hello" },
  });
  expect(useGraphStore.getState().params?.["param1"].value).toBe("hello");
});

test("clicking remove deletes the param row and restores the empty state", () => {
  render(<FlowParamsPanel />);
  fireEvent.click(screen.getByTestId("flow-params-add"));
  fireEvent.click(screen.getByTestId("flow-param-remove-param1"));
  expect(screen.queryByTestId("flow-param-param1")).not.toBeInTheDocument();
  expect(screen.getByTestId("flow-params-empty")).toBeInTheDocument();
});
