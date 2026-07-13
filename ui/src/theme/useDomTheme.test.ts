import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { useDomTheme } from "./useDomTheme";

beforeEach(() => {
  document.documentElement.dataset.theme = "dark";
});

describe("useDomTheme", () => {
  test("returns dark when data-theme is dark", () => {
    const { result } = renderHook(() => useDomTheme());
    expect(result.current).toBe("dark");
  });

  test("returns light when data-theme is light before render", () => {
    document.documentElement.dataset.theme = "light";
    const { result } = renderHook(() => useDomTheme());
    expect(result.current).toBe("light");
  });

  test("reacts to data-theme changes after mount", async () => {
    const { result } = renderHook(() => useDomTheme());
    expect(result.current).toBe("dark");

    document.documentElement.dataset.theme = "light";
    await waitFor(() => {
      expect(result.current).toBe("light");
    });
  });
});
