import { describe, expect, test } from "vitest";

import type { EdgeModel } from "../store/model";
import { toRFEdge } from "./toReactFlow";

const edge: EdgeModel = {
  id: "e1",
  source: { node_id: "a", port_id: "pa" },
  target: { node_id: "b", port_id: "pb" },
};

describe("toRFEdge", () => {
  test("compatible === false marks the edge incompatible and carries the reason", () => {
    const rfEdge = toRFEdge(edge, false, false, "Expected int, got str");

    expect(rfEdge.type).toBe("cmEdge");
    expect(rfEdge.source).toBe("a");
    expect(rfEdge.sourceHandle).toBe("pa");
    expect(rfEdge.target).toBe("b");
    expect(rfEdge.targetHandle).toBe("pb");
    expect(rfEdge.data?.incompatible).toBe(true);
    expect(rfEdge.data?.reason).toBe("Expected int, got str");
  });

  test("null verdict (unknown) does not mark the edge incompatible", () => {
    const rfEdge = toRFEdge(edge, false, null, null);

    expect(rfEdge.data?.incompatible).toBe(false);
  });

  test("undefined verdict (not yet validated) does not mark the edge incompatible", () => {
    const rfEdge = toRFEdge(edge, false, undefined, undefined);

    expect(rfEdge.data?.incompatible).toBe(false);
  });

  test("selected flag passes through", () => {
    const rfEdge = toRFEdge(edge, true, undefined, undefined);

    expect(rfEdge.selected).toBe(true);
  });
});
