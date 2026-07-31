import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { SelectionToolbar } from "./SelectionToolbar";

describe("SelectionToolbar", () => {
  test("renders the node count, run buttons, and group buttons when callbacks are provided", () => {
    render(
      <SelectionToolbar
        count={3}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={vi.fn()}
        onUngroup={vi.fn()}
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

    const groupBtn = screen.getByTestId("group-selection");
    expect(groupBtn).toBeInTheDocument();
    expect(groupBtn).toHaveTextContent("Group");

    const ungroupBtn = screen.getByTestId("ungroup-selection");
    expect(ungroupBtn).toBeInTheDocument();
    expect(ungroupBtn).toHaveTextContent("Ungroup");
  });

  test("omitting onGroup hides the Group button", () => {
    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("group-selection")).not.toBeInTheDocument();
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

  test("passing onGroup renders a Group button and clicking it calls onGroup once", () => {
    const onGroup = vi.fn();

    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onGroup={onGroup}
      />,
    );

    const groupBtn = screen.getByTestId("group-selection");
    expect(groupBtn).toBeInTheDocument();
    expect(groupBtn).toHaveTextContent("Group");

    fireEvent.click(groupBtn);

    expect(onGroup).toHaveBeenCalledTimes(1);
  });

  test("passing onUngroup renders an Ungroup button and clicking it calls onUngroup once", () => {
    const onUngroup = vi.fn();

    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onUngroup={onUngroup}
      />,
    );

    const ungroupBtn = screen.getByTestId("ungroup-selection");
    expect(ungroupBtn).toBeInTheDocument();
    expect(ungroupBtn).toHaveTextContent("Ungroup");

    fireEvent.click(ungroupBtn);

    expect(onUngroup).toHaveBeenCalledTimes(1);
  });

  test("passing onExtractToComposite renders an Extract to composite button and clicking it calls onExtractToComposite once", () => {
    const onExtractToComposite = vi.fn();

    render(
      <SelectionToolbar
        count={2}
        onRunSelectedOnly={vi.fn()}
        onRunToSelected={vi.fn()}
        onExtractToComposite={onExtractToComposite}
      />,
    );

    const extractBtn = screen.getByTestId("extract-to-composite");
    expect(extractBtn).toBeInTheDocument();
    expect(extractBtn).toHaveTextContent("Extract to composite");

    fireEvent.click(extractBtn);

    expect(onExtractToComposite).toHaveBeenCalledTimes(1);
  });
});
