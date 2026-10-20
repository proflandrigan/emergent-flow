import { beforeEach, describe, expect, test } from "vitest";

import { useTraceStore } from "./traceStore";

beforeEach(() => {
  useTraceStore.getState().reset();
});

describe("initial state", () => {
  test("default state is selection-downstream with empty families", () => {
    const s = useTraceStore.getState();
    expect(s.mode).toBe("selection-downstream");
    expect(s.families).toEqual([]);
  });
});

describe("setReach", () => {
  test("sets reach mode and direction", () => {
    useTraceStore.getState().setReach("upstream");
    const s = useTraceStore.getState();
    expect(s.mode).toBe("reach");
    expect(s.direction).toBe("upstream");
  });

  test("clears families set by a previous lens", () => {
    useTraceStore.getState().toggleFamily("ml");
    useTraceStore.getState().setReach("upstream");
    expect(useTraceStore.getState().families).toEqual([]);
  });
});

describe("route", () => {
  test("startRoutePick sets route mode awaiting a target", () => {
    useTraceStore.getState().startRoutePick("a");
    const s = useTraceStore.getState();
    expect(s.mode).toBe("route");
    expect(s.routeFrom).toBe("a");
    expect(s.routeTo).toBeNull();
    expect(s.routePicking).toBe(true);
  });

  test("setRoute completes the route", () => {
    useTraceStore.getState().startRoutePick("a");
    useTraceStore.getState().setRoute("a", "b");
    const s = useTraceStore.getState();
    expect(s.routePicking).toBe(false);
    expect(s.routeTo).toBe("b");
  });
});

describe("toggleFamily", () => {
  test("adds, accumulates, removes, and resets when emptied", () => {
    const { toggleFamily } = useTraceStore.getState();

    toggleFamily("ml");
    expect(useTraceStore.getState().mode).toBe("lens");
    expect(useTraceStore.getState().families).toEqual(["ml"]);

    useTraceStore.getState().toggleFamily("clean");
    expect(useTraceStore.getState().families).toEqual(["ml", "clean"]);

    useTraceStore.getState().toggleFamily("ml");
    expect(useTraceStore.getState().families).toEqual(["clean"]);

    useTraceStore.getState().toggleFamily("clean");
    const s = useTraceStore.getState();
    expect(s.mode).toBe("selection-downstream");
    expect(s.families).toEqual([]);
  });
});

describe("reset", () => {
  test("reset after setRoute clears everything", () => {
    useTraceStore.getState().setRoute("a", "b");
    useTraceStore.getState().reset();
    const s = useTraceStore.getState();
    expect(s.mode).toBe("selection-downstream");
    expect(s.direction).toBe("downstream");
    expect(s.routeFrom).toBeNull();
    expect(s.routeTo).toBeNull();
    expect(s.routePicking).toBe(false);
    expect(s.families).toEqual([]);
  });
});
