import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { IconButton } from "./IconButton";

test("renders its children", () => {
  render(
    <IconButton aria-label="Search">
      <span data-testid="icon">icon</span>
    </IconButton>,
  );
  expect(screen.getByTestId("icon")).toBeInTheDocument();
});

test("requires and forwards aria-label", () => {
  render(
    <IconButton aria-label="Search">
      <span>icon</span>
    </IconButton>,
  );
  expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
});

test("calls onClick when clicked", () => {
  const handleClick = vi.fn();
  render(
    <IconButton aria-label="Search" onClick={handleClick}>
      <span>icon</span>
    </IconButton>,
  );
  fireEvent.click(screen.getByRole("button"));
  expect(handleClick).toHaveBeenCalledTimes(1);
});
