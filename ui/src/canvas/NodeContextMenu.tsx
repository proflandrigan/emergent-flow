// A minimal right-click context menu for canvas nodes. Positioned at the mouse coordinates the
// triggering `contextmenu` event reports (fixed-position, so no pane/viewport coordinate math is
// needed). Currently a single item, "Run to here" (Epic 7 Story 5); deliberately not a generic
// menu framework -- add items here directly if/when more are needed.

import type { CSSProperties } from "react";

export interface NodeContextMenuProps {
  x: number;
  y: number;
  onRunToHere: () => void;
  onClose: () => void;
}

const menuStyle: CSSProperties = {
  position: "fixed",
  zIndex: 1000,
  background: "#fff",
  border: "1px solid #ccc",
  borderRadius: 4,
  boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
  padding: "0.25rem 0",
  fontSize: 13,
};

const itemStyle: CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "0.35rem 0.75rem",
  background: "none",
  border: "none",
  cursor: "pointer",
};

export function NodeContextMenu({
  x,
  y,
  onRunToHere,
  onClose,
}: NodeContextMenuProps): JSX.Element {
  return (
    <div data-testid="node-context-menu" style={{ ...menuStyle, left: x, top: y }}>
      <button
        type="button"
        data-testid="node-context-menu-run-to-here"
        style={itemStyle}
        onClick={() => {
          onRunToHere();
          onClose();
        }}
      >
        Run to here ▸
      </button>
    </div>
  );
}
