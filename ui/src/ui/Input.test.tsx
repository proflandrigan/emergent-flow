import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { Input } from "./Input";

test("renders and accepts typed input", () => {
  const handleChange = vi.fn();
  render(<Input value="" onChange={handleChange} />);
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "test" } });
  expect(handleChange).toHaveBeenCalledTimes(1);
});

test("pill prop toggles pill class", () => {
  const { rerender } = render(<Input />);
  const input = screen.getByRole("textbox");
  expect(input.className).not.toContain("ef-input--pill");

  rerender(<Input pill />);
  expect(input.className).toContain("ef-input--pill");
});

test("leadingIcon renders when provided and is absent when not", () => {
  const { rerender } = render(<Input />);
  expect(screen.queryByTestId("leading-icon")).not.toBeInTheDocument();

  rerender(<Input leadingIcon={<span data-testid="leading-icon">🔍</span>} />);
  expect(screen.getByTestId("leading-icon")).toBeInTheDocument();
});

test("forwards data-testid and placeholder", () => {
  render(<Input data-testid="my-input" placeholder="Search..." />);
  const input = screen.getByTestId("my-input");
  expect(input).toHaveAttribute("placeholder", "Search...");
});
