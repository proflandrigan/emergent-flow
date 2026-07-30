import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { NodeContextMenu } from "./NodeContextMenu";

const defaultProps = () => ({
  onRunToHere: vi.fn(),
  onRunThisNode: vi.fn(),
  onRunFromHere: vi.fn(),
  onNodeInfo: vi.fn(),
  onClose: vi.fn(),
});

describe("NodeContextMenu", () => {
  test("renders the Run to here item at the given x/y position", () => {
    render(
      <NodeContextMenu
        x={100}
        y={200}
        {...defaultProps()}
      />,
    );

    const menu = screen.getByTestId("node-context-menu");
    expect(menu).toHaveStyle({ left: "100px", top: "200px" });

    const item = screen.getByTestId("node-context-menu-run-to-here");
    expect(item).toBeInTheDocument();
    expect(item).toHaveTextContent("Run to here ▸");
  });

  test("clicking Run to here calls onRunToHere once and onClose once", () => {
    const props = defaultProps();

    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...props}
      />,
    );

    fireEvent.click(screen.getByTestId("node-context-menu-run-to-here"));

    expect(props.onRunToHere).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  test("renders the Run this node item", () => {
    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...defaultProps()}
      />,
    );

    const item = screen.getByTestId("node-context-menu-run-this-node");
    expect(item).toBeInTheDocument();
    expect(item).toHaveTextContent("Run this node");
  });

  test("clicking Run this node calls onRunThisNode once and onClose once", () => {
    const props = defaultProps();

    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...props}
      />,
    );

    fireEvent.click(screen.getByTestId("node-context-menu-run-this-node"));

    expect(props.onRunThisNode).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  test("renders the Run from here item", () => {
    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...defaultProps()}
      />,
    );

    const item = screen.getByTestId("node-context-menu-run-from-here");
    expect(item).toBeInTheDocument();
    expect(item).toHaveTextContent("Run from here ▾");
  });

  test("clicking Run from here calls onRunFromHere once and onClose once", () => {
    const props = defaultProps();

    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...props}
      />,
    );

    fireEvent.click(screen.getByTestId("node-context-menu-run-from-here"));

    expect(props.onRunFromHere).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  test("renders the Node info item", () => {
    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...defaultProps()}
      />,
    );

    const item = screen.getByTestId("node-context-menu-node-info");
    expect(item).toBeInTheDocument();
    expect(item).toHaveTextContent("Node info");
  });

  test("clicking Node info calls onNodeInfo once and onClose once", () => {
    const props = defaultProps();

    render(
      <NodeContextMenu
        x={0}
        y={0}
        {...props}
      />,
    );

    fireEvent.click(screen.getByTestId("node-context-menu-node-info"));

    expect(props.onNodeInfo).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
