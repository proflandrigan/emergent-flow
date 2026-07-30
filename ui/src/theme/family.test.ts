import { describe, expect, test } from "vitest";

import { FAMILY, familyMeta } from "./family";

const KNOWN = ["data", "clean", "stats", "ml", "nn", "reports"] as const;

describe("FAMILY", () => {
  for (const key of KNOWN) {
    test(`${key} is present with correct structure`, () => {
      const entry = FAMILY[key];
      expect(entry.label).toBeTruthy();
      expect(entry.label.length).toBeGreaterThan(0);
      expect(entry.color).toMatch(/^var\(--fam-/);
      expect(entry.soft).toMatch(/^var\(--fam-/);
      expect(entry.Icon).toBeDefined();
    });
  }
});

describe("every FAMILY entry is fully themed", () => {
  for (const [family, meta] of Object.entries(FAMILY)) {
    // Guards against a family shipping with the grey `familyMeta` fallback, and
    // against a hue token whose name has drifted from its family key (the token
    // pairs live in ui/src/styles/tokens.css).
    test(`${family} has a label and family-named hue tokens`, () => {
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.label).not.toBe(family);
      expect(meta.color).toBe(`var(--fam-${family})`);
      expect(meta.soft).toBe(`var(--fam-${family}-soft)`);
      expect(meta.Icon).toBeDefined();
    });
  }
});

describe("familyMeta passthrough", () => {
  for (const key of KNOWN) {
    test(`${key} returns FAMILY[key]`, () => {
      expect(familyMeta(key)).toBe(FAMILY[key]);
    });
  }
});

describe("familyMeta fallback", () => {
  const UNKNOWN = "nonexistent-family";

  test("returns fallback for unknown family", () => {
    const fallback = familyMeta(UNKNOWN);
    expect(fallback.label).toBe(UNKNOWN);
    expect(fallback.color).toBe("var(--text-secondary)");
    expect(fallback.soft).toBe("var(--surface-2)");
    expect(fallback.Icon).toBeDefined();
  });
});
