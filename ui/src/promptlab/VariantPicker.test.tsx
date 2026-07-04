import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { DEFAULT_VARIANTS } from "./providerModels";
import { VariantPicker } from "./VariantPicker";

test("renders one checkbox per default variant", () => {
  render(<VariantPicker selected={[]} onChange={vi.fn()} />);
  expect(screen.getAllByRole("checkbox")).toHaveLength(DEFAULT_VARIANTS.length);
});

test("reflects selected variants as checked", () => {
  render(<VariantPicker selected={[DEFAULT_VARIANTS[0]]} onChange={vi.fn()} />);
  DEFAULT_VARIANTS.forEach((variant, i) => {
    const checkbox = screen.getByTestId(
      `variant-checkbox-${variant.provider}:${variant.model}`,
    );
    if (i === 0) {
      expect(checkbox).toBeChecked();
    } else {
      expect(checkbox).not.toBeChecked();
    }
  });
});

test("checking an unselected variant calls onChange with it appended", () => {
  const onChange = vi.fn();
  render(<VariantPicker selected={[]} onChange={onChange} />);
  const variant = DEFAULT_VARIANTS[0];
  const checkbox = screen.getByTestId(
    `variant-checkbox-${variant.provider}:${variant.model}`,
  );
  fireEvent.click(checkbox);
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith([variant]);
});

test("unchecking a selected variant calls onChange with it removed", () => {
  const onChange = vi.fn();
  render(
    <VariantPicker
      selected={[DEFAULT_VARIANTS[0], DEFAULT_VARIANTS[1]]}
      onChange={onChange}
    />,
  );
  const variant = DEFAULT_VARIANTS[0];
  const checkbox = screen.getByTestId(
    `variant-checkbox-${variant.provider}:${variant.model}`,
  );
  fireEvent.click(checkbox);
  expect(onChange).toHaveBeenCalledTimes(1);
  const result = onChange.mock.calls[0][0];
  expect(result).toHaveLength(1);
  expect(result[0]).toEqual(DEFAULT_VARIANTS[1]);
});
