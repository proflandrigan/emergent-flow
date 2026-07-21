import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { NodeContextMenu } from "./NodeContextMenu";

describe("NodeContextMenu", () => {
  test("renders the Run to here item at the given x/y position", () => {
    render(
      <NodeContextMenu
        x={100}
        y={200}
        onRunToHere={vi.fn()}
        onNodeInfo={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const menu = screen.getByTestId("node-context-menu");
    expect(menu).toHaveStyle({ left: "100px", top: "200px" });

    const item = screen.getByTestId("node-context-menu-run-to-here");
    expect(item).toBeInTheDocument();
    expect(item).toHaveTextContent("Run to here ▸");
  });

  test("clicking Run to here calls onRunToHere once and onClose once", () => {
    const onRunToHere = vi.fn();
    const onClose = vi.fn();

    render(
      <NodeContextMenu
        x={0}
        y={0}
        onRunToHere={onRunToHere}
        onNodeInfo={vi.fn()}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByTestId("node-context-menu-run-to-here"));

    expect(onRunToHere).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("renders the Node info item", () => {
    render(
      <NodeContextMenu
        x={0}
        y={0}
        onRunToHere={vi.fn()}
        onNodeInfo={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const item = screen.getByTestId("node-context-menu-node-info");
    expect(item).toBeInTheDocument();
    expect(item).toHaveTextContent("Node info");
  });

  test("clicking Node info calls onNodeInfo once and onClose once", () => {
    const onNodeInfo = vi.fn();
    const onClose = vi.fn();

    render(
      <NodeContextMenu
        x={0}
        y={0}
        onRunToHere={vi.fn()}
        onNodeInfo={onNodeInfo}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByTestId("node-context-menu-node-info"));

    expect(onNodeInfo).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
