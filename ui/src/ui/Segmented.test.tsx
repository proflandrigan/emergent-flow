import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { Segmented } from "./Segmented";

test("renders all options' labels", () => {
  render(
    <Segmented
      options={[
        { value: "config", label: "Config" },
        { value: "code", label: "Code" },
        { value: "results", label: "Results" },
      ]}
      value="config"
      onChange={() => {}}
    />,
  );
  expect(screen.getByText("Config")).toBeInTheDocument();
  expect(screen.getByText("Code")).toBeInTheDocument();
  expect(screen.getByText("Results")).toBeInTheDocument();
});

test("clicking an inactive option calls onChange with that option's value", () => {
  const handleChange = vi.fn();
  render(
    <Segmented
      options={[
        { value: "a", label: "A" },
        { value: "b", label: "B" },
      ]}
      value="a"
      onChange={handleChange}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "B" }));
  expect(handleChange).toHaveBeenCalledWith("b");
  expect(handleChange).toHaveBeenCalledTimes(1);
});

test("active option has aria-pressed true, inactive options have false", () => {
  render(
    <Segmented
      options={[
        { value: "x", label: "X" },
        { value: "y", label: "Y" },
        { value: "z", label: "Z" },
      ]}
      value="y"
      onChange={() => {}}
    />,
  );
  expect(screen.getByRole("button", { name: "X" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  expect(screen.getByRole("button", { name: "Y" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "Z" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("forwards aria-label to group", () => {
  render(
    <Segmented
      options={[{ value: "a", label: "A" }]}
      value="a"
      onChange={() => {}}
      aria-label="View mode"
    />,
  );
  expect(screen.getByRole("group")).toHaveAttribute("aria-label", "View mode");
});

test("type safety — generic value type", () => {
  type TabId = "config" | "code" | "results";
  const options: TabId[] = ["config", "code", "results"];
  const handleChange = vi.fn();
  render(
    <Segmented<TabId>
      options={options.map((v) => ({ value: v, label: v }))}
      value="config"
      onChange={handleChange}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "code" }));
  expect(handleChange).toHaveBeenCalledWith("code" as TabId);
});
