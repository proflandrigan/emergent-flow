import { beforeEach, describe, expect, test, vi } from "vitest";

import type { Graph } from "../generated/ir";
import { parseViewHash } from "../io/viewLink";
import type { Tour } from "../session/sessionClient";
import { useGraphStore } from "./graphStore";
import type { NodeModel } from "./model";
import { useSelectionStore } from "./selectionStore";
import { useSubgraphStore } from "./subgraphStore";
import { resolveBreadcrumbs, useTourStore } from "./tourStore";
import { useTraceStore } from "./traceStore";
import { useViewLinkStore } from "./viewLinkStore";

function makeNode(id: string, subgraph?: Graph | null): NodeModel {
  return {
    id,
    type: "data.fake",
    label: id,
    paradigm: "functional",
    params: [],
    ports: [],
    position: { x: 0, y: 0 },
    groupId: null,
    subgraph,
  };
}

function makeTour(id: string, steps = 3): Tour {
  return {
    id,
    title: `Tour ${id}`,
    author: "agent",
    conclusion: "done",
    steps: Array.from({ length: steps }, (_, i) => ({ note: `step ${i}`, focus: ["n1"] })),
  };
}

function emptyGraph(nodes: Graph["nodes"] = {}): Graph {
  return { nodes, edges: {} } as unknown as Graph;
}

function seedGraph(): void {
  useGraphStore.setState({
    nodes: { n1: makeNode("n1"), n2: makeNode("n2"), n3: makeNode("n3") },
    edges: {},
  });
}

beforeEach(() => {
  useTourStore.setState({
    playing: null,
    snapshot: null,
    pendingViewportRestore: null,
    announcement: null,
  });
  useTraceStore.getState().reset();
  useSelectionStore.getState().clear();
  useSubgraphStore.getState().clear();
  useViewLinkStore.setState({ pendingCanvas: null, pendingTour: null });
  window.history.replaceState(null, "", "/");
  seedGraph();
});

describe("start", () => {
  test("captures the snapshot once and keeps it when switching tours", () => {
    useSelectionStore.getState().replaceSelection(["n1"]);
    useTourStore.getState().start(makeTour("t1"));
    const first = useTourStore.getState().snapshot;
    expect(first?.selection.nodes).toEqual({ n1: true });

    useTourStore.getState().start(makeTour("t2"));
    expect(useTourStore.getState().snapshot).toBe(first);
    expect(useTourStore.getState().playing?.tour.id).toBe("t2");
  });

  test("clears selection and breadcrumbs, drives trace, and writes the hash", () => {
    window.history.replaceState(null, "", "/?session=s1");
    useSelectionStore.getState().replaceSelection(["n1"]);
    useSubgraphStore
      .getState()
      .pushSubgraph({ compositeId: "n1", label: "n1", subgraph: emptyGraph() });

    const tour = makeTour("t1");
    useTourStore.getState().start(tour);

    expect(useSelectionStore.getState().nodes).toEqual({});
    expect(useSubgraphStore.getState().breadcrumbs).toEqual([]);
    expect(useTraceStore.getState().mode).toBe("tour");
    expect(useTraceStore.getState().tourStep).toEqual(tour.steps[0]);
    expect(window.location.hash).toBe("#tour=t1&step=0");
    expect(window.location.search).toBe("?session=s1");
    expect(useTourStore.getState().announcement).toBe("Step 1 of 3: Tour t1");
  });

  test("clamps a bad start index", () => {
    useTourStore.getState().start(makeTour("t1"), -4);
    expect(useTourStore.getState().playing?.index).toBe(0);
    useTourStore.getState().exit();
    useTourStore.getState().start(makeTour("t1"), 99);
    expect(useTourStore.getState().playing?.index).toBe(2);
  });
});

describe("navigation", () => {
  test("next and prev clamp at the ends", () => {
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().prev();
    expect(useTourStore.getState().playing?.index).toBe(0);
    useTourStore.getState().next();
    useTourStore.getState().next();
    useTourStore.getState().next();
    expect(useTourStore.getState().playing?.index).toBe(2);
  });

  test("goTo uses replaceState only and fires no hashchange", () => {
    useTourStore.getState().start(makeTour("t1"));
    const replace = vi.spyOn(window.history, "replaceState");
    const push = vi.spyOn(window.history, "pushState");
    const onHashChange = vi.fn();
    window.addEventListener("hashchange", onHashChange);

    useTourStore.getState().goTo(2);

    expect(replace).toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
    expect(onHashChange).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#tour=t1&step=2");

    window.removeEventListener("hashchange", onHashChange);
    replace.mockRestore();
    push.mockRestore();
  });

  test("navigation is a no-op when not playing", () => {
    useTourStore.getState().next();
    useTourStore.getState().goTo(1);
    expect(useTourStore.getState().playing).toBeNull();
  });
});

describe("captureViewport", () => {
  test("only stores the first value", () => {
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().captureViewport({ x: 1, y: 2, zoom: 1 });
    useTourStore.getState().captureViewport({ x: 9, y: 9, zoom: 2 });
    expect(useTourStore.getState().snapshot?.viewport).toEqual({ x: 1, y: 2, zoom: 1 });
  });
});

describe("exit", () => {
  test("restores selection minus deleted ids, reach trace, hash and viewport", () => {
    window.history.replaceState(null, "", "/#focus=n1");
    useSelectionStore.getState().replaceSelection(["n1", "n2"]);
    useTraceStore.getState().setReach("upstream");

    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().captureViewport({ x: 5, y: 6, zoom: 1.5 });

    const { n2: _removed, ...rest } = useGraphStore.getState().nodes;
    void _removed;
    useGraphStore.setState({ nodes: rest });

    useTourStore.getState().exit();

    expect(useSelectionStore.getState().nodes).toEqual({ n1: true });
    expect(useTraceStore.getState().mode).toBe("reach");
    expect(useTraceStore.getState().direction).toBe("upstream");
    expect(window.location.hash).toBe("#focus=n1");
    expect(useTourStore.getState().pendingViewportRestore).toEqual({ x: 5, y: 6, zoom: 1.5 });
    expect(useTourStore.getState().playing).toBeNull();
    expect(useTourStore.getState().announcement).toBe("Tour closed");

    useTourStore.getState().consumeViewportRestore();
    expect(useTourStore.getState().pendingViewportRestore).toBeNull();
  });

  test("a tour-link hash is restored to no hash", () => {
    window.history.replaceState(null, "", "/#tour=t1&step=0");
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().exit();
    expect(window.location.hash).toBe("");
    expect(parseViewHash(window.location.hash).tour).toBeNull();
  });

  test("restores a route only when both endpoints still exist", () => {
    useTraceStore.getState().setRoute("n1", "n3");
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().exit();
    expect(useTraceStore.getState().mode).toBe("route");
    expect(useTraceStore.getState().routeTo).toBe("n3");

    useTraceStore.getState().setRoute("n1", "n3");
    useTourStore.getState().start(makeTour("t1"));
    const { n3: _removed, ...rest } = useGraphStore.getState().nodes;
    void _removed;
    useGraphStore.setState({ nodes: rest });
    useTourStore.getState().exit();
    expect(useTraceStore.getState().mode).toBe("selection-downstream");
  });

  test("restore:false leaves selection alone and resets trace only in tour mode", () => {
    useTourStore.getState().start(makeTour("t1"));
    useSelectionStore.getState().replaceSelection(["n2"]);
    useTourStore.getState().exit({ restore: false });
    expect(useSelectionStore.getState().nodes).toEqual({ n2: true });
    expect(useTraceStore.getState().mode).toBe("selection-downstream");

    useTourStore.getState().start(makeTour("t1"));
    useTraceStore.getState().setReach("downstream");
    useTourStore.getState().exit({ restore: false });
    expect(useTraceStore.getState().mode).toBe("reach");
  });
});

describe("updateTour", () => {
  test("clamps the index when steps shrink and announces", () => {
    useTourStore.getState().start(makeTour("t1"), 2);
    useTourStore.getState().updateTour(makeTour("t1", 2));
    expect(useTourStore.getState().playing?.index).toBe(1);
    expect(useTourStore.getState().announcement).toBe("Tour updated — now at step 2 of 2");

    useTourStore.getState().updateTour(makeTour("t1", 4));
    expect(useTourStore.getState().playing?.index).toBe(1);
    expect(useTourStore.getState().announcement).toBe("Tour updated");
  });

  test("ignores a different tour id", () => {
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().updateTour(makeTour("other", 1));
    expect(useTourStore.getState().playing?.tour.id).toBe("t1");
  });
});

describe("resolveBreadcrumbs", () => {
  test("rebuilds a 2-level path and truncates at a missing composite", () => {
    const inner = emptyGraph();
    const outer = emptyGraph({ c2: { subgraph: inner } } as unknown as Graph["nodes"]);
    const nodes = { c1: makeNode("c1", outer) };
    const stale = emptyGraph();
    const snapshot = [
      { compositeId: "c1", label: "One", subgraph: stale },
      { compositeId: "c2", label: "Two", subgraph: stale },
    ];

    const resolved = resolveBreadcrumbs(snapshot, nodes);
    expect(resolved.map((b) => b.compositeId)).toEqual(["c1", "c2"]);
    expect(resolved[0].subgraph).toBe(outer);
    expect(resolved[1].subgraph).toBe(inner);
    expect(resolved[1].label).toBe("Two");

    const truncated = resolveBreadcrumbs(snapshot, { c1: makeNode("c1", emptyGraph()) });
    expect(truncated.map((b) => b.compositeId)).toEqual(["c1"]);
    expect(resolveBreadcrumbs(snapshot, {})).toEqual([]);
  });
});

describe("integration", () => {
  test("a new external view link exits playback", () => {
    useTourStore.getState().start(makeTour("t1"));
    useViewLinkStore.getState().request(parseViewHash("#focus=n1"));
    expect(useTourStore.getState().playing).toBeNull();
    expect(useViewLinkStore.getState().pendingCanvas?.focus).toEqual(["n1"]);
  });

  test("playback never mutates the graph", () => {
    const before = JSON.stringify(useGraphStore.getState().toIR());
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().next();
    useTourStore.getState().exit();
    expect(JSON.stringify(useGraphStore.getState().toIR())).toBe(before);
  });
});

describe("trace takeover", () => {
  test("another trace mode taking over ends playback without restoring", () => {
    useSelectionStore.getState().replaceSelection(["n1"]);
    useTourStore.getState().start(makeTour("t1"));
    useSelectionStore.getState().replaceSelection(["n2"]);

    useTraceStore.getState().setReach("upstream");

    expect(useTourStore.getState().playing).toBeNull();
    expect(useTraceStore.getState().mode).toBe("reach");
    expect(useSelectionStore.getState().nodes).toEqual({ n2: true });
  });

  test("stepping through a tour does not end it", () => {
    useTourStore.getState().start(makeTour("t1"));
    useTourStore.getState().next();
    expect(useTourStore.getState().playing?.index).toBe(1);
  });
});
