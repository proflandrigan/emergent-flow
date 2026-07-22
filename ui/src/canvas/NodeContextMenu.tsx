// A minimal right-click context menu for canvas nodes. Positioned at the mouse coordinates the
// triggering `contextmenu` event reports (fixed-position, so no pane/viewport coordinate math is
// needed). Currently two items, "Run to here" and "Node info"; deliberately not a generic menu
// framework -- add items here directly if/when more are needed.

import { Menu } from "../ui/Menu";

export interface NodeContextMenuProps {
  x: number;
  y: number;
  onRunToHere: () => void;
  onNodeInfo: () => void;
  onClose: () => void;
}

export function NodeContextMenu({
  x,
  y,
  onRunToHere,
  onNodeInfo,
  onClose,
}: NodeContextMenuProps): JSX.Element {
  return (
    <div
      data-testid="node-context-menu"
      style={{ position: "fixed", zIndex: 1000, left: x, top: y }}
    >
      <Menu
        items={[
          {
            label: "Run to here ▸",
            testId: "node-context-menu-run-to-here",
            onSelect: () => {
              onRunToHere();
              onClose();
            },
          },
          {
            label: "Node info",
            testId: "node-context-menu-node-info",
            onSelect: () => {
              onNodeInfo();
              onClose();
            },
          },
        ]}
        aria-label="Node context menu"
      />
    </div>
  );
}

export default NodeContextMenu;
