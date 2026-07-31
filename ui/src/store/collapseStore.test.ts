import { beforeEach, describe, expect, test } from "vitest";

import { isGroupCollapsed, useCollapseStore } from "./collapseStore";

beforeEach(() => {
  useCollapseStore.setState({ collapsed: {} });
});

describe("isGroupCollapsed", () => {
  test("returns false for a group never toggled", () => {
    expect(isGroupCollapsed(useCollapseStore.getState(), "g1")).toBe(false);
  });

  test("returns true after toggling once", () => {
    useCollapseStore.getState().toggleCollapsed("g1");
    expect(isGroupCollapsed(useCollapseStore.getState(), "g1")).toBe(true);
  });

  test("toggling twice returns to expanded", () => {
    useCollapseStore.getState().toggleCollapsed("g1");
    useCollapseStore.getState().toggleCollapsed("g1");
    expect(isGroupCollapsed(useCollapseStore.getState(), "g1")).toBe(false);
  });
});

describe("setCollapsed", () => {
  test("sets the exact collapsed state regardless of current value", () => {
    useCollapseStore.getState().setCollapsed("g1", true);
    expect(isGroupCollapsed(useCollapseStore.getState(), "g1")).toBe(true);

    useCollapseStore.getState().setCollapsed("g1", true);
    expect(isGroupCollapsed(useCollapseStore.getState(), "g1")).toBe(true);

    useCollapseStore.getState().setCollapsed("g1", false);
    expect(isGroupCollapsed(useCollapseStore.getState(), "g1")).toBe(false);
  });

  test("toggling one group does not affect another", () => {
    useCollapseStore.getState().setCollapsed("g1", true);
    expect(isGroupCollapsed(useCollapseStore.getState(), "g2")).toBe(false);
  });
});

describe("clear", () => {
  test("empties all collapsed state", () => {
    useCollapseStore.getState().setCollapsed("g1", true);
    useCollapseStore.getState().setCollapsed("g2", true);

    useCollapseStore.getState().clear();

    expect(useCollapseStore.getState().collapsed).toEqual({});
  });
});
