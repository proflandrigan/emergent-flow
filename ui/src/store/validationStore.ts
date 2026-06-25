// Validation state holds the last `/validate` verdict and is the single source of truth for
// edge-compatibility colouring. Status tracks whether validation is in-flight, idle, or
// failed; diagnostics and edgeCompatibility are never cleared on error (a transient server
// error must not wipe the last-known-good verdicts).

import { create } from "zustand";

import type { Diagnostic, Diagnostics } from "./validation";

export interface ValidationStore {
  status: "idle" | "validating" | "ok" | "error";
  diagnostics: Diagnostic[];
  edgeCompatibility: Record<string, boolean | null>;
  error: string | null;
  setValidating: () => void;
  setResult: (d: Diagnostics) => void;
  setError: (message: string) => void;
  clear: () => void;
}

export const useValidationStore = create<ValidationStore>((set) => ({
  status: "idle",
  diagnostics: [],
  edgeCompatibility: {},
  error: null,

  setValidating() {
    set({ status: "validating" });
  },

  setResult(d) {
    set({
      diagnostics: d.diagnostics,
      edgeCompatibility: d.edge_compatibility,
      status: "ok",
      error: null,
    });
  },

  setError(message) {
    set({ status: "error", error: message });
  },

  clear() {
    set({ status: "idle", diagnostics: [], edgeCompatibility: {}, error: null });
  },
}));
