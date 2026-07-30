import { afterEach, beforeEach, describe, expect, test } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { supportedSchemaVersion } from "../store/validateIR";
import { clearSession, recoverSession, saveSession } from "./sessionRecovery";

const catalogNode = {
  type: "load_csv",
  label: "Load CSV",
  paradigm: "functional" as const,
  family: "data",
  version: 1,
  ports: [
    { name: "path", direction: "in" as const, data_type: "str" },
    { name: "df", direction: "out" as const, data_type: "DataFrame" },
  ],
  params: [{ name: "path", type_token: "str", default: "" }],
};

describe("sessionRecovery", () => {
  beforeEach(() => {
    localStorage.clear();
    useGraphStore.getState().reset();
  });

  afterEach(() => {
    localStorage.clear();
    useGraphStore.getState().reset();
  });

  describe("saveSession / recoverSession round-trip", () => {
    test("returns null when nothing is stored", () => {
      expect(recoverSession()).toBeNull();
    });

    test("round-trips a non-empty graph", () => {
      useGraphStore.getState().addNodeFromSpec(catalogNode, { x: 0, y: 0 });
      saveSession();
      const recovered = recoverSession();
      expect(recovered).not.toBeNull();
      expect(recovered!.graph.nodes).toBeDefined();
      expect(Object.keys(recovered!.graph.nodes ?? {}).length).toBe(1);
    });

    test("returns null for empty graph (no nodes)", () => {
      saveSession();
      expect(recoverSession()).toBeNull();
    });

    test("recoverSession clears a persisted empty graph", () => {
      saveSession();
      // saveSession writes unconditionally; recoverSession rejects + clears empty graphs
      expect(recoverSession()).toBeNull();
      expect(localStorage.getItem("ef-session-recovery")).toBeNull();
    });

    test("clears stale schema version", () => {
      localStorage.setItem(
        "ef-session-recovery",
        JSON.stringify({
          schema_version: supportedSchemaVersion + 999,
          graph: { nodes: { n1: {} }, edges: {} },
          saved_at: Date.now(),
        }),
      );
      expect(recoverSession()).toBeNull();
      expect(localStorage.getItem("ef-session-recovery")).toBeNull();
    });

    test("clears corrupt JSON", () => {
      localStorage.setItem("ef-session-recovery", "NOT JSON");
      expect(recoverSession()).toBeNull();
      expect(localStorage.getItem("ef-session-recovery")).toBeNull();
    });

    test("clears a blob whose graph field is missing", () => {
      localStorage.setItem(
        "ef-session-recovery",
        JSON.stringify({
          schema_version: supportedSchemaVersion,
          saved_at: Date.now(),
        }),
      );
      expect(recoverSession()).toBeNull();
      expect(localStorage.getItem("ef-session-recovery")).toBeNull();
    });

    test("returns the saved_at timestamp alongside the graph", () => {
      useGraphStore.getState().addNodeFromSpec(catalogNode, { x: 0, y: 0 });
      const before = Date.now();
      saveSession();
      const recovered = recoverSession();
      expect(recovered).not.toBeNull();
      expect(recovered!.savedAt).toBeGreaterThanOrEqual(before);
    });
  });

  describe("clearSession", () => {
    test("removes the stored blob", () => {
      localStorage.setItem("ef-session-recovery", "test");
      clearSession();
      expect(localStorage.getItem("ef-session-recovery")).toBeNull();
    });

    test("is a no-op when nothing is stored", () => {
      expect(() => clearSession()).not.toThrow();
      expect(localStorage.getItem("ef-session-recovery")).toBeNull();
    });
  });
});
