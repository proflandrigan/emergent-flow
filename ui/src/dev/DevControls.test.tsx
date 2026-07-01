import { expect, test } from "vitest";

import { getDevMenuItems } from "./DevControls";

// Vitest runs in dev mode by default (import.meta.env.DEV is true), so this exercises the
// "has nodes" branch; there is no established pattern in this repo for stubbing
// import.meta.env, so the DEV=false branch is not separately tested here.
test("returns a single menu item wired to load a large graph", () => {
  const items = getDevMenuItems();
  expect(items).toHaveLength(1);
  expect(items[0].label).toBe("Load 1000 nodes");
  expect(items[0].testId).toBe("dev-load-large");
  expect(typeof items[0].onSelect).toBe("function");
});
