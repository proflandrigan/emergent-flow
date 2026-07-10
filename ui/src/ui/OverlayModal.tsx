import { X } from "lucide-react";
import { useEffect, type JSX, type ReactNode } from "react";
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
  // Escape closes the modal, mirroring the new X button -- without this, the close
  // button is the only way to dismiss without a mouse click on the backdrop.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

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
        role="dialog"
        aria-modal="true"
        style={{
          width,
          maxHeight: "70vh",
          overflow: "auto",
          // Extra top padding reserves room for the absolutely-positioned close
          // button below so it never overlaps flowing content (e.g. a long
          // header row) that starts at the top of the panel.
          padding: "calc(var(--space-4) + var(--space-5)) var(--space-4) var(--space-4)",
          position: "relative",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          aria-label="Close"
          data-testid="overlay-modal-close"
          onClick={onClose}
          style={{
            position: "absolute",
            top: "var(--space-2)",
            right: "var(--space-2)",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-secondary)",
            padding: "var(--space-1)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <X size={16} />
        </button>
        {children}
      </div>
    </div>,
    document.body,
  );
}
