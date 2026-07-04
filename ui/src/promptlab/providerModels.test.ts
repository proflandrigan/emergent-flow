import { describe, expect, test } from "vitest";

import { DEFAULT_VARIANTS } from "./providerModels";

describe("providerModels", () => {
  test("has at least the three documented Anthropic variants", () => {
    expect(DEFAULT_VARIANTS.length).toBeGreaterThanOrEqual(3);
    expect(DEFAULT_VARIANTS.some((v) => v.model === "claude-sonnet-5")).toBe(
      true,
    );
    expect(DEFAULT_VARIANTS.some((v) => v.model === "claude-opus-4-8")).toBe(
      true,
    );
    expect(
      DEFAULT_VARIANTS.some((v) => v.model === "claude-haiku-4-5-20251001"),
    ).toBe(true);
  });

  test('every entry has provider "anthropic"', () => {
    expect(DEFAULT_VARIANTS.every((v) => v.provider === "anthropic")).toBe(
      true,
    );
  });
});
