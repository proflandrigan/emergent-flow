import "@testing-library/jest-dom/vitest";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver =
  globalThis.ResizeObserver ??
  (ResizeObserver as unknown as typeof globalThis.ResizeObserver);
