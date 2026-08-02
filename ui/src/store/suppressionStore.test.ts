import { beforeEach, expect, test } from "vitest";

import { ruleMeta } from "./validityRules";
import { useSuppressionStore } from "./suppressionStore";

beforeEach(() => {
  localStorage.clear();
  useSuppressionStore.getState().clear();
});

test("suppress/unsuppress round-trips and persists to localStorage", () => {
  const s = useSuppressionStore.getState();
  expect(s.isSuppressed("fit_before_split", "scale")).toBe(false);
  s.suppress("fit_before_split", "scale", "intentional demo");
  expect(useSuppressionStore.getState().isSuppressed("fit_before_split", "scale")).toBe(true);
  expect(JSON.parse(localStorage.getItem("ef-suppressions")!)).toEqual({
    "fit_before_split::scale": "intentional demo",
  });
  useSuppressionStore.getState().unsuppress("fit_before_split", "scale");
  expect(useSuppressionStore.getState().isSuppressed("fit_before_split", "scale")).toBe(false);
});

test("suppression is per (rule_id, node_id)", () => {
  const s = useSuppressionStore.getState();
  s.suppress("fit_before_split", "scale", "why");
  expect(s.isSuppressed("fit_before_split", "split")).toBe(false);
  expect(s.isSuppressed("window_crosses_split", "scale")).toBe(false);
  expect(s.isSuppressed(null, "scale")).toBe(false);
  expect(s.isSuppressed("fit_before_split", null)).toBe(false);
});

test("ruleMeta resolves a rule and returns undefined for unknown", () => {
  const meta = ruleMeta("fit_before_split");
  expect(meta?.title).toBe("Transform fitted before the train/test split");
  expect(meta?.severity).toBe("error");
  expect(ruleMeta("nope")).toBeUndefined();
  expect(ruleMeta(null)).toBeUndefined();
});
