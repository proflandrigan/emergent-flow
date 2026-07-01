import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useTheme } from "./useTheme";

function createMatchMedia(matches: boolean) {
  return vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  localStorage.clear();
  window.matchMedia = createMatchMedia(false);
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

test("no stored value, prefers-color-scheme:light does NOT match → dark", () => {
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("dark");
});

test("no stored value, prefers-color-scheme:light DOES match → light", () => {
  window.matchMedia = createMatchMedia(true);
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("light");
});

test("stored value in localStorage wins over matchMedia", () => {
  localStorage.setItem("ef-theme", "light");
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("light");
});

test("toggleTheme flips between dark and light and persists", () => {
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("dark");

  act(() => {
    result.current.toggleTheme();
  });
  expect(result.current.theme).toBe("light");
  expect(localStorage.getItem("ef-theme")).toBe("light");

  act(() => {
    result.current.toggleTheme();
  });
  expect(result.current.theme).toBe("dark");
  expect(localStorage.getItem("ef-theme")).toBe("dark");
});

test("setTheme sets the value explicitly and persists", () => {
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("dark");

  act(() => {
    result.current.setTheme("light");
  });
  expect(result.current.theme).toBe("light");
  expect(localStorage.getItem("ef-theme")).toBe("light");
});

test("data-theme is set on document.documentElement", () => {
  const { result } = renderHook(() => useTheme());
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

  act(() => {
    result.current.toggleTheme();
  });
  expect(document.documentElement.getAttribute("data-theme")).toBe("light");
});
