import type { JSX, ReactNode } from "react";

export interface OverlayModalProps {
  width: number;
  onClose: () => void;
  children: ReactNode;
}

// Shared backdrop + centered panel for the overflow menu's "Manage connections"/
// "Browse schema" overlays -- one place for backdrop/centering/click-outside-to-close
// behavior instead of duplicating it per overlay.
export function OverlayModal({
  width,
  onClose,
  children,
}: OverlayModalProps): JSX.Element {
  return (
    <div
      style={{
        position: "absolute",
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
    </div>
  );
}
