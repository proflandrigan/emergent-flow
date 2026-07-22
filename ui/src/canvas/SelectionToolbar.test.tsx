import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { SelectionToolbar } from "./SelectionToolbar";

describe("SelectionToolbar", () => {
  test("renders the node count and a Run selected button", () => {
    render(
      <SelectionToolbar count={3} onRunSelected={vi.fn()} />,
    );

    const toolbar = screen.getByTestId("selection-toolbar");
    expect(toolbar).toBeInTheDocument();
    expect(toolbar).toHaveTextContent("3 nodes selected");

    const button = screen.getByTestId("run-selected");
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("Run selected");
  });

  test("clicking Run selected calls onRunSelected once", () => {
    const onRunSelected = vi.fn();

    render(
      <SelectionToolbar count={2} onRunSelected={onRunSelected} />,
    );

    fireEvent.click(screen.getByTestId("run-selected"));

    expect(onRunSelected).toHaveBeenCalledTimes(1);
  });
});
