import { useRef, useState, type CSSProperties, type JSX } from "react";
import "./ResizeHandle.css";

export interface ResizeHandleProps {
  /** Viewport edge the panel is docked to; drag direction is inverted for "right". */
  dock: "left" | "right";
  width: number;
  min: number;
  max: number;
  /** Width restored by double-click / Home -- the panel's original hardcoded width. */
  resetWidth: number;
  onWidthChange: (width: number) => void;
  /** Lets the dock drop its width transition while dragging (see App.tsx). */
  onResizingChange?: (resizing: boolean) => void;
  label: string;
  testId?: string;
  /** Placement only (top/bottom/left/right); the rest comes from ResizeHandle.css. */
  style?: CSSProperties;
}

const KEY_STEP = 16;
const KEY_STEP_LARGE = 48;

// Drag handle for the side docks (palette, inspector). Uses pointer capture rather than
// document-level listeners so a fast drag that outruns the 8px hit area still tracks the
// cursor, and so the drag survives crossing over the React Flow canvas.
export function ResizeHandle({
  dock,
  width,
  min,
  max,
  resetWidth,
  onWidthChange,
  onResizingChange,
  label,
  testId,
  style,
}: ResizeHandleProps): JSX.Element {
  // Start coords live in a ref (pointermove fires far too often to re-render for), while
  // `dragging` is state purely so the handle can style itself mid-drag.
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  function clamp(next: number): number {
    return Math.min(max, Math.max(min, Math.round(next)));
  }

  function commit(deltaX: number): void {
    if (drag.current === null) return;
    // A right-docked panel grows as the pointer moves left, so the delta is inverted.
    const delta = dock === "right" ? -deltaX : deltaX;
    onWidthChange(clamp(drag.current.startWidth + delta));
  }

  return (
    <div
      className="ef-resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      data-testid={testId}
      data-resizing={dragging}
      style={style}
      onPointerDown={(e) => {
        // Suppresses the text-selection / native drag that would otherwise start
        // mid-resize and leave the page with a stray selection.
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { startX: e.clientX, startWidth: width };
        setDragging(true);
        onResizingChange?.(true);
      }}
      onPointerMove={(e) => {
        if (drag.current === null) return;
        commit(e.clientX - drag.current.startX);
      }}
      onPointerUp={(e) => {
        if (drag.current === null) return;
        commit(e.clientX - drag.current.startX);
        e.currentTarget.releasePointerCapture(e.pointerId);
        drag.current = null;
        setDragging(false);
        onResizingChange?.(false);
      }}
      onPointerCancel={() => {
        drag.current = null;
        setDragging(false);
        onResizingChange?.(false);
      }}
      onDoubleClick={() => onWidthChange(clamp(resetWidth))}
      onKeyDown={(e) => {
        const step = e.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
        const grow = dock === "right" ? "ArrowLeft" : "ArrowRight";
        const shrink = dock === "right" ? "ArrowRight" : "ArrowLeft";
        if (e.key === grow) {
          e.preventDefault();
          onWidthChange(clamp(width + step));
        } else if (e.key === shrink) {
          e.preventDefault();
          onWidthChange(clamp(width - step));
        } else if (e.key === "Home") {
          e.preventDefault();
          onWidthChange(clamp(resetWidth));
        }
      }}
    />
  );
}
