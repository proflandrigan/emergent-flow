import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { InputSetTable } from "./InputSetTable";

test("empty variables shows the single-run note, no table", () => {
  render(<InputSetTable variables={[]} rows={[]} onChange={vi.fn()} />);
  expect(screen.getByText(/single run mode/i)).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
});

test("renders one column header per variable", () => {
  render(
    <InputSetTable
      variables={["question", "persona"]}
      rows={[]}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText("question")).toBeInTheDocument();
  expect(screen.getByText("persona")).toBeInTheDocument();
});

test("renders row cells bound to row values", () => {
  render(
    <InputSetTable
      variables={["question"]}
      rows={[{ question: "2+2?" }]}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByTestId("input-set-cell-0-question")).toHaveValue("2+2?");
});

test("editing a cell calls onChange with the updated row, others untouched", () => {
  const onChange = vi.fn();
  render(
    <InputSetTable
      variables={["a", "b"]}
      rows={[
        { a: "1", b: "2" },
        { a: "3", b: "4" },
      ]}
      onChange={onChange}
    />,
  );
  fireEvent.change(screen.getByTestId("input-set-cell-0-a"), {
    target: { value: "9" },
  });
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith([
    { a: "9", b: "2" },
    { a: "3", b: "4" },
  ]);
});

test('clicking "Add row" appends an empty row', () => {
  const onChange = vi.fn();
  render(
    <InputSetTable variables={["q"]} rows={[{ q: "x" }]} onChange={onChange} />,
  );
  fireEvent.click(screen.getByTestId("input-set-add-row"));
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith([{ q: "x" }, { q: "" }]);
});

test("clicking remove on a row calls onChange without that row", () => {
  const onChange = vi.fn();
  render(
    <InputSetTable
      variables={["q"]}
      rows={[{ q: "x" }, { q: "y" }]}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByTestId("input-set-remove-0"));
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith([{ q: "y" }]);
});
