import "@testing-library/jest-dom/vitest";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver =
  globalThis.ResizeObserver ??
  (ResizeObserver as unknown as typeof globalThis.ResizeObserver);

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom implements neither PointerEvent nor pointer capture, so without these a
// fireEvent.pointerDown/Move carries no clientX (drag deltas come out NaN) and any handler
// calling setPointerCapture throws. Needed by the pointer-driven dock ResizeHandle.
class PointerEventPolyfill extends MouseEvent {
  readonly pointerId: number;

  constructor(type: string, params: PointerEventInit = {}) {
    super(type, params);
    this.pointerId = params.pointerId ?? 0;
  }
}
globalThis.PointerEvent =
  globalThis.PointerEvent ??
  (PointerEventPolyfill as unknown as typeof globalThis.PointerEvent);

if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}
