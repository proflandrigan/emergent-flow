import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { Toast } from "./Toast";

test("renders the message", () => {
  render(<Toast message="Hello" />);
  expect(screen.getByText("Hello")).toBeInTheDocument();
});

test("info variant applies info class", () => {
  render(<Toast message="Info" variant="info" />);
  const toast = screen.getByRole("alert");
  expect(toast.className).toContain("ef-toast--info");
});

test("error variant applies error class", () => {
  render(<Toast message="Error" variant="error" />);
  const toast = screen.getByRole("alert");
  expect(toast.className).toContain("ef-toast--error");
});

test("dismiss button appears when onDismiss is provided", () => {
  render(<Toast message="Dismiss me" onDismiss={() => {}} />);
  expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
});

test("dismiss button is not rendered when onDismiss is not provided", () => {
  render(<Toast message="No dismiss" />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("clicking dismiss calls onDismiss", () => {
  const handleDismiss = vi.fn();
  render(<Toast message="Dismiss me" onDismiss={handleDismiss} />);
  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(handleDismiss).toHaveBeenCalledTimes(1);
});
