import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { LabelControls } from "./LabelControls";

test("renders Pass and Fail buttons", () => {
  render(<LabelControls onLabel={() => {}} />);

  expect(screen.getByTestId("label-pass")).toBeInTheDocument();
  expect(screen.getByTestId("label-fail")).toBeInTheDocument();
});

test('clicking Pass calls onLabel("pass")', () => {
  const onLabel = vi.fn();
  render(<LabelControls onLabel={onLabel} />);

  fireEvent.click(screen.getByTestId("label-pass"));

  expect(onLabel).toHaveBeenCalledTimes(1);
  expect(onLabel).toHaveBeenCalledWith("pass");
});

test('clicking Fail calls onLabel("fail")', () => {
  const onLabel = vi.fn();
  render(<LabelControls onLabel={onLabel} />);

  fireEvent.click(screen.getByTestId("label-fail"));

  expect(onLabel).toHaveBeenCalledTimes(1);
  expect(onLabel).toHaveBeenCalledWith("fail");
});

test("aria-pressed reflects the current label prop", () => {
  render(<LabelControls label="pass" onLabel={() => {}} />);

  expect(screen.getByTestId("label-pass")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByTestId("label-fail")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});
