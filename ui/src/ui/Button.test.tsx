import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { Button } from "./Button";

test("renders children text", () => {
  render(<Button>Click me</Button>);
  expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
});

test("calls onClick when clicked", () => {
  const handleClick = vi.fn();
  render(<Button onClick={handleClick}>Click</Button>);
  fireEvent.click(screen.getByRole("button"));
  expect(handleClick).toHaveBeenCalledTimes(1);
});

test("does not call onClick when disabled", () => {
  const handleClick = vi.fn();
  render(
    <Button onClick={handleClick} disabled>
      Click
    </Button>,
  );
  const button = screen.getByRole("button");
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(handleClick).not.toHaveBeenCalled();
});

test.each(["primary", "secondary", "ghost", "icon"] as const)(
  "renders %s variant without throwing and applies variant class",
  (variant) => {
    render(<Button variant={variant}>Btn</Button>);
    const button = screen.getByRole("button");
    expect(button.className).toContain(`ef-button--${variant}`);
  },
);

test("forwards data-testid and aria-label to the underlying button", () => {
  render(
    <Button data-testid="my-btn" aria-label="Custom label">
      Click
    </Button>,
  );
  const button = screen.getByTestId("my-btn");
  expect(button).toHaveAttribute("aria-label", "Custom label");
});
