import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { Tooltip } from "./Tooltip";

test("renders the wrapped child", () => {
  render(
    <Tooltip label="help">
      <span data-testid="child">●</span>
    </Tooltip>,
  );
  expect(screen.getByTestId("child")).toBeInTheDocument();
});

test("tooltip text is not visible by default", () => {
  render(
    <Tooltip label="help text">
      <span data-testid="trigger">●</span>
    </Tooltip>,
  );
  expect(screen.queryByText("help text")).not.toBeInTheDocument();
});

test("becomes visible on mouseEnter and hides on mouseLeave", () => {
  const { container } = render(
    <Tooltip label="help text">
      <span data-testid="trigger">●</span>
    </Tooltip>,
  );
  const wrapper = container.querySelector(".ef-tooltip")!;

  fireEvent.mouseEnter(wrapper);
  expect(screen.getByText("help text")).toBeInTheDocument();

  fireEvent.mouseLeave(wrapper);
  expect(screen.queryByText("help text")).not.toBeInTheDocument();
});

test("shows on focus and hides on blur of the wrapper", () => {
  const { container } = render(
    <Tooltip label="help">
      <button data-testid="btn">Click</button>
    </Tooltip>,
  );
  const wrapper = container.querySelector(".ef-tooltip")!;

  fireEvent.focus(wrapper);
  expect(screen.getByText("help")).toBeInTheDocument();

  fireEvent.blur(wrapper);
  expect(screen.queryByText("help")).not.toBeInTheDocument();
});

test("preserves child data-testid", () => {
  render(
    <Tooltip label="help">
      <span data-testid="my-child">content</span>
    </Tooltip>,
  );
  expect(screen.getByTestId("my-child")).toBeInTheDocument();
});
