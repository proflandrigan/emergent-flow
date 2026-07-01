import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { Menu } from "./Menu";

test("renders all item labels", () => {
  render(
    <Menu
      items={[
        { label: "Item A", onSelect: () => {} },
        { label: "Item B", onSelect: () => {} },
      ]}
    />,
  );
  expect(screen.getByText("Item A")).toBeInTheDocument();
  expect(screen.getByText("Item B")).toBeInTheDocument();
});

test("clicking an enabled item calls its onSelect", () => {
  const handleSelect = vi.fn();
  render(<Menu items={[{ label: "Item", onSelect: handleSelect }]} />);
  fireEvent.click(screen.getByRole("menuitem", { name: "Item" }));
  expect(handleSelect).toHaveBeenCalledTimes(1);
});

test("clicking a disabled item does NOT call its onSelect", () => {
  const handleSelect = vi.fn();
  render(
    <Menu
      items={[{ label: "Item", onSelect: handleSelect, disabled: true }]}
    />,
  );
  const item = screen.getByRole("menuitem", { name: "Item" });
  expect(item).toBeDisabled();
  fireEvent.click(item);
  expect(handleSelect).not.toHaveBeenCalled();
});

test("disabled item renders as a disabled button", () => {
  render(
    <Menu items={[{ label: "Item", onSelect: () => {}, disabled: true }]} />,
  );
  expect(screen.getByRole("menuitem", { name: "Item" })).toBeDisabled();
});

test("menu has role menu", () => {
  render(<Menu items={[{ label: "Item", onSelect: () => {} }]} />);
  expect(screen.getByRole("menu")).toBeInTheDocument();
});

test("forwards aria-label to the menu container", () => {
  render(
    <Menu
      items={[{ label: "Item", onSelect: () => {} }]}
      aria-label="Actions"
    />,
  );
  expect(screen.getByRole("menu", { name: "Actions" })).toBeInTheDocument();
});
