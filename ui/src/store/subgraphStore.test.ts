import { afterEach, describe, expect, test } from "vitest";

import { useSubgraphStore, breadcrumbLabels, currentSubgraph } from "./subgraphStore";

function makeSubgraph() {
  return {
    paradigm: "functional" as const,
    nodes: {
      n1: {
        id: "n1",
        type: "data.load_csv",
        label: null,
        paradigm: "functional" as const,
        position: { x: 0, y: 0 },
        params: [],
        ports: [],
        group_id: null,
      },
    },
    edges: {},
  };
}

afterEach(() => {
  useSubgraphStore.getState().clear();
});

describe("useSubgraphStore", () => {
  test("starts empty (top-level view)", () => {
    const state = useSubgraphStore.getState();
    expect(state.breadcrumbs).toEqual([]);
  });

  test("pushSubgraph adds a breadcrumb entry", () => {
    const sub = makeSubgraph();
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c1",
      label: "Composite 1",
      subgraph: sub,
    });

    const state = useSubgraphStore.getState();
    expect(state.breadcrumbs).toHaveLength(1);
    expect(state.breadcrumbs[0].label).toBe("Composite 1");
    expect(state.breadcrumbs[0].compositeId).toBe("c1");
  });

  test("pushSubgraph supports nested subgraphs", () => {
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c1",
      label: "Outer",
      subgraph: makeSubgraph(),
    });
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c2",
      label: "Inner",
      subgraph: makeSubgraph(),
    });

    const state = useSubgraphStore.getState();
    expect(state.breadcrumbs).toHaveLength(2);
    expect(state.breadcrumbs[0].label).toBe("Outer");
    expect(state.breadcrumbs[1].label).toBe("Inner");
  });

  test("popTo removes entries after the given depth", () => {
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c1",
      label: "A",
      subgraph: makeSubgraph(),
    });
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c2",
      label: "B",
      subgraph: makeSubgraph(),
    });

    useSubgraphStore.getState().popTo(1);
    const state = useSubgraphStore.getState();
    expect(state.breadcrumbs).toHaveLength(1);
    expect(state.breadcrumbs[0].label).toBe("A");
  });

  test("popTo(0) clears the stack (returns to top-level)", () => {
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c1",
      label: "A",
      subgraph: makeSubgraph(),
    });

    useSubgraphStore.getState().popTo(0);
    expect(useSubgraphStore.getState().breadcrumbs).toHaveLength(0);
  });

  test("clear resets the stack", () => {
    useSubgraphStore.getState().pushSubgraph({
      compositeId: "c1",
      label: "A",
      subgraph: makeSubgraph(),
    });
    useSubgraphStore.getState().clear();

    expect(useSubgraphStore.getState().breadcrumbs).toHaveLength(0);
  });
});

describe("currentSubgraph", () => {
  test("returns null when at top-level", () => {
    expect(currentSubgraph({ breadcrumbs: [] })).toBeNull();
  });

  test("returns the last entry's subgraph", () => {
    const sub = makeSubgraph();
    const result = currentSubgraph({ breadcrumbs: [{ compositeId: "c1", label: "Test", subgraph: sub }] });
    expect(result).toBe(sub);
  });
});

describe("breadcrumbLabels", () => {
  test("top-level returns just Top-level", () => {
    expect(breadcrumbLabels({ breadcrumbs: [] })).toEqual(["Top-level"]);
  });

  test("single level includes Top-level plus the composite label", () => {
    expect(
      breadcrumbLabels({
        breadcrumbs: [{ compositeId: "c1", label: "My Composite", subgraph: makeSubgraph() }],
      }),
    ).toEqual(["Top-level", "My Composite"]);
  });

  test("nested levels show the full path", () => {
    expect(
      breadcrumbLabels({
        breadcrumbs: [
          { compositeId: "c1", label: "A", subgraph: makeSubgraph() },
          { compositeId: "c2", label: "B", subgraph: makeSubgraph() },
        ],
      }),
    ).toEqual(["Top-level", "A", "B"]);
  });
});
