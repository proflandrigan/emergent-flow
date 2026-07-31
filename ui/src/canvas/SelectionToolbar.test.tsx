import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { SelectionToolbar } from "./SelectionToolbar";

describe("SelectionToolbar", () => {
  test("renders the node count, run buttons, and group buttons", () => {
    render(
      <SelectionToolbar
        count={3}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={vi.fn()}
        onUngroup={vi.fn()}
        canUngroup={false}
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

    const groupBtn = screen.getByTestId("group-nodes");
    expect(groupBtn).toBeInTheDocument();
    expect(groupBtn).toHaveTextContent("Group");

    const ungroupBtn = screen.getByTestId("ungroup-nodes");
    expect(ungroupBtn).toBeInTheDocument();
    expect(ungroupBtn).toHaveTextContent("Ungroup");
  });

  test("Ungroup button is disabled when canUngroup is false", () => {
    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={vi.fn()}
        onUngroup={vi.fn()}
        canUngroup={false}
      />,
    );
    expect(screen.getByTestId("ungroup-nodes")).toBeDisabled();
  });

  test("Ungroup button is enabled when canUngroup is true", () => {
    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={vi.fn()}
        onUngroup={vi.fn()}
        canUngroup={true}
      />,
    );
    expect(screen.getByTestId("ungroup-nodes")).toBeEnabled();
  });

  test("clicking Group calls onGroup once", () => {
    const onGroup = vi.fn();
    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={onGroup}
        onUngroup={vi.fn()}
        canUngroup={false}
      />,
    );
    fireEvent.click(screen.getByTestId("group-nodes"));
    expect(onGroup).toHaveBeenCalledTimes(1);
  });

  test("clicking Ungroup calls onUngroup once", () => {
    const onUngroup = vi.fn();
    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={vi.fn()}
        onUngroup={onUngroup}
        canUngroup={true}
      />,
    );
    fireEvent.click(screen.getByTestId("ungroup-nodes"));
    expect(onUngroup).toHaveBeenCalledTimes(1);
  });

  test("clicking Run selected only calls onRunSelectedOnly once", () => {
    const onRunSelectedOnly = vi.fn();

    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={onRunSelectedOnly}
        onRunToSelected={vi.fn()}
        onGroup={vi.fn()}
        onUngroup={vi.fn()}
        canUngroup={false}
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
        onGroup={vi.fn()}
        onUngroup={vi.fn()}
        canUngroup={false}
      />,
    );

    fireEvent.click(screen.getByTestId("run-to-selected"));

    expect(onRunToSelected).toHaveBeenCalledTimes(1);
  });
});
