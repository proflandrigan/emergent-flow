import { describe, expect, test } from "vitest";

import { isDetailed, LOD_ZOOM_THRESHOLD } from "./lod";

describe("lod", () => {
  test("threshold is 0.4", () => {
    expect(LOD_ZOOM_THRESHOLD).toBe(0.4);
  });

  test("isDetailed(1) is true", () => {
    expect(isDetailed(1)).toBe(true);
  });

  test("isDetailed(0.4) is true (boundary inclusive)", () => {
    expect(isDetailed(0.4)).toBe(true);
  });

  test("isDetailed(0.39) is false", () => {
    expect(isDetailed(0.39)).toBe(false);
  });

  test("isDetailed(0.1) is false", () => {
    expect(isDetailed(0.1)).toBe(false);
  });
});
