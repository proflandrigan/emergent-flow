import type { JSX, ReactNode } from "react";
import { createPortal } from "react-dom";

export interface OverlayModalProps {
  width: number;
  onClose: () => void;
  children: ReactNode;
}

// Shared backdrop + centered panel for the overflow menu's "Manage connections"/
// "Browse schema" overlays -- one place for backdrop/centering/click-outside-to-close
// behavior instead of duplicating it per overlay.
//
// Portaled to document.body: callers may mount this deep inside a positioned/scrolling
// ancestor (e.g. the Inspector's `position: absolute; overflow: auto` dock panel). Without
// the portal, `position: absolute` would resolve relative to that ancestor and the "full
// screen" backdrop would be clipped to its box instead of covering the viewport; `position:
// fixed` here is relative to the viewport regardless of where this ends up in the DOM.
export function OverlayModal({
  width,
  onClose,
  children,
}: OverlayModalProps): JSX.Element {
  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 30,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0, 0, 0, 0.4)",
      }}
      onClick={onClose}
    >
      <div
        className="glass"
        style={{
          width,
          maxHeight: "70vh",
          overflow: "auto",
          padding: "var(--space-4)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
