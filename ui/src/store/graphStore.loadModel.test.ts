import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { generateLargeGraph } from "../dev/generateLargeGraph";
import type { ExecuteResponse } from "./execution";
import { useExecutionStore } from "./executionStore";
import { useGraphStore } from "./graphStore";
import { useValidationStore } from "./validationStore";

beforeEach(() => {
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
  useValidationStore.getState().clear();
});

describe("loadModel", () => {
  test("loads a model and updates store nodes", () => {
    const spec: CatalogNode = {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [{ name: "out", direction: "out" }],
      params: [],
    };

    const model = generateLargeGraph(spec, 10);
    useGraphStore.getState().loadModel(model);

    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(10);
  });

  test("undo restores prior state with single history entry", () => {
    const spec: CatalogNode = {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [{ name: "out", direction: "out" }],
      params: [],
    };

    const model = generateLargeGraph(spec, 10);
    useGraphStore.getState().loadModel(model);

    // After loadModel, we should have 1 entry in past (the empty state)
    expect(useGraphStore.getState().past).toHaveLength(1);

    // Undo should restore empty state
    useGraphStore.getState().undo();
    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(0);
  });

  test("clears stale execution + validation verdicts on whole-graph replacement", () => {
    // Seed both derived stores as if a prior graph had been run/validated. Node and edge ids
    // are preserved across export -> re-import, so without clearing these would be displayed
    // against the freshly loaded graph.
    const fakeRun: ExecuteResponse = {
      payload_version: 2,
      results: { "node:old": { out: { kind: "scalar", value: 1 } } },
      statuses: { "node:old": { status: "ok" } },
    };
    useExecutionStore.getState().setResult(fakeRun);
    useValidationStore.getState().setResult({
      diagnostics: [{ severity: "error", code: "type_incompatible", message: "x", edge_id: "e:old" }],
      edge_compatibility: { "e:old": false },
    });

    const spec: CatalogNode = {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [{ name: "out", direction: "out" }],
      params: [],
    };
    useGraphStore.getState().loadModel(generateLargeGraph(spec, 3));

    expect(useExecutionStore.getState().results).toEqual({});
    expect(useExecutionStore.getState().statuses).toEqual({});
    expect(useValidationStore.getState().diagnostics).toEqual([]);
    expect(useValidationStore.getState().edgeCompatibility).toEqual({});
  });
});
