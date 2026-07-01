import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { Select } from "./Select";

test("renders provided option children", () => {
  render(
    <Select>
      <option value="a">Option A</option>
      <option value="b">Option B</option>
    </Select>,
  );
  const select = screen.getByRole("combobox");
  expect(select).toBeInTheDocument();
  expect(screen.getByText("Option A")).toBeInTheDocument();
  expect(screen.getByText("Option B")).toBeInTheDocument();
});

test("onChange fires with the selected value", () => {
  const handleChange = vi.fn();
  render(
    <Select onChange={handleChange}>
      <option value="a">A</option>
      <option value="b">B</option>
    </Select>,
  );
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "b" } });
  expect(handleChange).toHaveBeenCalledTimes(1);
});

test("forwards disabled and data-testid", () => {
  render(
    <Select data-testid="my-select" disabled>
      <option value="a">A</option>
    </Select>,
  );
  const select = screen.getByTestId("my-select");
  expect(select).toBeDisabled();
});
