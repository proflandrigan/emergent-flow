import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { ResizeHandle } from "./ResizeHandle";

const PROPS = {
  dock: "right" as const,
  width: 320,
  min: 280,
  max: 720,
  resetWidth: 320,
  onWidthChange: vi.fn(),
  onResizingChange: vi.fn(),
  label: "Resize inspector",
  testId: "inspector-resize-handle",
};

function renderHandle(overrides: Partial<typeof PROPS> = {}) {
  const onWidthChange = vi.fn();
  const onResizingChange = vi.fn();
  const { rerender } = render(
    <ResizeHandle
      {...PROPS}
      {...overrides}
      onWidthChange={onWidthChange}
      onResizingChange={onResizingChange}
    />,
  );
  return {
    handle: screen.getByTestId("inspector-resize-handle"),
    onWidthChange,
    onResizingChange,
    rerender,
  };
}

test("dragging the pointer left widens a right-docked panel", () => {
  const { handle, onWidthChange } = renderHandle();
  fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
  fireEvent.pointerMove(handle, { clientX: 460, pointerId: 1 });
  // delta X = -40; right-dock inverts it to +40 -> 320 + 40 = 360.
  expect(onWidthChange).toHaveBeenLastCalledWith(360);
});

test("dragging the pointer right narrows a right-docked panel", () => {
  const { handle, onWidthChange } = renderHandle();
  fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
  fireEvent.pointerMove(handle, { clientX: 530, pointerId: 1 });
  // delta X = +30; right-dock inverts it to -30 -> 320 - 30 = 290.
  expect(onWidthChange).toHaveBeenLastCalledWith(290);
});

test("width is clamped to [min, max]", () => {
  const { handle, onWidthChange } = renderHandle();
  // Haul the pointer far to the left -> clamped to the 720 ceiling.
  fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
  fireEvent.pointerMove(handle, { clientX: 0, pointerId: 1 });
  expect(onWidthChange).toHaveBeenLastCalledWith(720);

  // Haul the pointer far to the right -> clamped to the 280 floor.
  fireEvent.pointerUp(handle, { clientX: 0, pointerId: 1 });
  fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
  fireEvent.pointerMove(handle, { clientX: 1000, pointerId: 1 });
  expect(onWidthChange).toHaveBeenLastCalledWith(280);
});

test("pointer-move without a prior pointer-down is a no-op", () => {
  const { handle, onWidthChange } = renderHandle();
  fireEvent.pointerMove(handle, { clientX: 100, pointerId: 1 });
  expect(onWidthChange).not.toHaveBeenCalled();
});

test("onResizingChange brackets the drag with true then false", () => {
  const { handle, onResizingChange } = renderHandle();
  fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
  expect(onResizingChange).toHaveBeenLastCalledWith(true);
  fireEvent.pointerUp(handle, { clientX: 500, pointerId: 1 });
  expect(onResizingChange).toHaveBeenLastCalledWith(false);
});

test("pointercancel abandons the drag and signals resize end", () => {
  const { handle, onWidthChange, onResizingChange } = renderHandle();
  fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
  fireEvent.pointerMove(handle, { clientX: 480, pointerId: 1 });
  expect(onWidthChange).toHaveBeenCalledTimes(1);

  // The OS can hijack the pointer mid-drag (e.g. a system gesture) and fire
  // pointercancel instead of pointerup -- the handle must drop the drag and
  // signal resize-end so the dock's width transition isn't left suppressed.
  fireEvent.pointerCancel(handle, { pointerId: 1 });
  expect(onResizingChange).toHaveBeenLastCalledWith(false);

  // A stray pointermove after cancel must not resume the abandoned drag.
  fireEvent.pointerMove(handle, { clientX: 400, pointerId: 1 });
  expect(onWidthChange).toHaveBeenCalledTimes(1);
});

test("double-click restores the reset width", () => {
  const { handle, onWidthChange } = renderHandle({ width: 400, resetWidth: 320 });
  fireEvent.doubleClick(handle);
  expect(onWidthChange).toHaveBeenLastCalledWith(320);
});

test("arrow keys grow/shrink, Shift scales the step, and Home resets", () => {
  const { handle, onWidthChange } = renderHandle();
  // Right-docked: ArrowLeft grows, ArrowRight shrinks.
  fireEvent.keyDown(handle, { key: "ArrowLeft" });
  expect(onWidthChange).toHaveBeenLastCalledWith(336);
  fireEvent.keyDown(handle, { key: "ArrowRight" });
  expect(onWidthChange).toHaveBeenLastCalledWith(304);
  // Shift scales the step from 16 to 48.
  fireEvent.keyDown(handle, { key: "ArrowLeft", shiftKey: true });
  expect(onWidthChange).toHaveBeenLastCalledWith(368);
  // Home restores the default.
  fireEvent.keyDown(handle, { key: "Home" });
  expect(onWidthChange).toHaveBeenLastCalledWith(320);
});

test("exposes separator role, aria min/now/max, and is focusable", () => {
  const { handle } = renderHandle();
  expect(handle).toHaveAttribute("role", "separator");
  expect(handle).toHaveAttribute("aria-valuenow", "320");
  expect(handle).toHaveAttribute("aria-valuemin", "280");
  expect(handle).toHaveAttribute("aria-valuemax", "720");
  expect(handle).toHaveAttribute("tabindex", "0");
});
