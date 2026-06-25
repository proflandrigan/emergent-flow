import { beforeEach, describe, expect, test } from "vitest";

import type { Diagnostics } from "./validation";
import { useValidationStore } from "./validationStore";

beforeEach(() => {
  useValidationStore.getState().clear();
});

describe("setResult", () => {
  test("populates diagnostics and edgeCompatibility and sets status to ok", () => {
    const diagnostics: Diagnostics = {
      diagnostics: [
        {
          severity: "error",
          code: "type_incompatible",
          message: "Expected int, got str",
          edge_id: "e1",
        },
      ],
      edge_compatibility: {
        e1: false,
        e2: true,
      },
    };

    useValidationStore.getState().setResult(diagnostics);

    const state = useValidationStore.getState();
    expect(state.diagnostics).toHaveLength(1);
    expect(state.diagnostics[0].code).toBe("type_incompatible");
    expect(state.edgeCompatibility).toEqual({ e1: false, e2: true });
    expect(state.status).toBe("ok");
    expect(state.error).toBeNull();
  });
});

describe("setError", () => {
  test("sets status to error and error message without clearing edgeCompatibility", () => {
    const diagnostics: Diagnostics = {
      diagnostics: [
        {
          severity: "warning",
          code: "deprecation",
          message: "This is deprecated",
        },
      ],
      edge_compatibility: {
        e1: true,
        e2: null,
      },
    };

    useValidationStore.getState().setResult(diagnostics);

    const beforeError = useValidationStore.getState().edgeCompatibility;
    expect(beforeError).toEqual({ e1: true, e2: null });

    useValidationStore.getState().setError("Server error");

    const state = useValidationStore.getState();
    expect(state.status).toBe("error");
    expect(state.error).toBe("Server error");
    expect(state.edgeCompatibility).toEqual(beforeError);
    expect(state.diagnostics).toHaveLength(1);
  });
});

describe("clear", () => {
  test("resets everything to initial state", () => {
    const diagnostics: Diagnostics = {
      diagnostics: [
        {
          severity: "error",
          code: "cycle_detected",
          message: "Cycle in graph",
          node_id: "n1",
        },
      ],
      edge_compatibility: {
        e1: false,
      },
    };

    useValidationStore.getState().setResult(diagnostics);
    useValidationStore.getState().setError("Previous error");

    useValidationStore.getState().clear();

    const state = useValidationStore.getState();
    expect(state.status).toBe("idle");
    expect(state.diagnostics).toEqual([]);
    expect(state.edgeCompatibility).toEqual({});
    expect(state.error).toBeNull();
  });
});
