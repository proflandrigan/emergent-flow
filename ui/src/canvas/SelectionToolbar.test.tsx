import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { SelectionToolbar } from "./SelectionToolbar";

describe("SelectionToolbar", () => {
  test("renders the node count and both run buttons", () => {
    render(
      <SelectionToolbar
        count={3}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
      />,
    );

    const toolbar = screen.getByTestId("selection-toolbar");
    expect(toolbar).toBeInTheDocument();
    expect(toolbar).toHaveTextContent("3 nodes selected");

    const onlyBtn = screen.getByTestId("run-selected-only");
    expect(onlyBtn).toBeInTheDocument();
    expect(onlyBtn).toHaveTextContent("Run selected only");

    const toBtn = screen.getByTestId("run-to-selected");
    expect(toBtn).toBeInTheDocument();
    expect(toBtn).toHaveTextContent("Run to selected");
  });

  test("clicking Run selected only calls onRunSelectedOnly once", () => {
    const onRunSelectedOnly = vi.fn();

    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={onRunSelectedOnly}
        onRunToSelected={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("run-selected-only"));

    expect(onRunSelectedOnly).toHaveBeenCalledTimes(1);
  });

  test("clicking Run to selected calls onRunToSelected once", () => {
    const onRunToSelected = vi.fn();

    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={onRunToSelected}
      />,
    );

    fireEvent.click(screen.getByTestId("run-to-selected"));

    expect(onRunToSelected).toHaveBeenCalledTimes(1);
  });
});
