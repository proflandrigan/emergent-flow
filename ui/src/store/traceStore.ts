// Ephemeral UI state selecting which highlight the canvas computes (selection downstream, reach,
// route, or family lens). Kept OUT of the store/IR, mirroring `collapseStore.ts` and
// `selectionStore.ts` (ADR 0014 Decision 3): trace state is never serialized into the graph.

import { create } from "zustand";

import type { TraceDirection } from "../canvas/trace";
import type { TourStep } from "../generated/tour";

/** Which highlight the canvas computes. "selection-downstream" is the default (downstream of selection). */
export type TraceStoreMode = "selection-downstream" | "reach" | "route" | "lens" | "tour";

export interface TraceStore {
  mode: TraceStoreMode;
  /** Reach direction; only meaningful when mode === "reach". Roots are the current selection. */
  direction: TraceDirection;
  /** Route endpoints; only meaningful when mode === "route". */
  routeFrom: string | null;
  routeTo: string | null;
  /** True while waiting for the user to click a route target (routeFrom set, routeTo null). */
  routePicking: boolean;
  /** Families highlighted by the lens; only meaningful when mode === "lens". */
  families: string[];
  /**
   * The guided-tour step driving the highlight; only meaningful when mode === "tour". The canvas
   * resolves it with resolveTourStep (exact focus, forward-only route).
   */
  tourStep: TourStep | null;
  /** Drive the highlight from a guided-tour step (replaces any other trace). */
  setTourStep: (step: TourStep) => void;
  setReach: (direction: TraceDirection) => void;
  startRoutePick: (fromId: string) => void;
  setRoute: (fromId: string, toId: string) => void;
  toggleFamily: (family: string) => void;
  /** Replace the lens wholesale (deep links, issue #168); an empty list resets to the default trace. */
  setLens: (families: string[]) => void;
  reset: () => void;
}

const INITIAL = {
  mode: "selection-downstream" as TraceStoreMode,
  direction: "downstream" as TraceDirection,
  routeFrom: null as string | null,
  routeTo: null as string | null,
  routePicking: false,
  families: [] as string[],
  tourStep: null as TourStep | null,
};

export const useTraceStore = create<TraceStore>((set, get) => ({
  ...INITIAL,

  setTourStep(step) {
    set({ ...INITIAL, mode: "tour", tourStep: step });
  },

  setReach(direction) {
    set({
      mode: "reach",
      direction,
      routeFrom: null,
      routeTo: null,
      routePicking: false,
      families: [],
      tourStep: null,
    });
  },

  startRoutePick(fromId) {
    set({
      mode: "route",
      direction: "downstream",
      routeFrom: fromId,
      routeTo: null,
      routePicking: true,
      families: [],
      tourStep: null,
    });
  },

  setRoute(fromId, toId) {
    set({
      mode: "route",
      direction: "downstream",
      routeFrom: fromId,
      routeTo: toId,
      routePicking: false,
      families: [],
      tourStep: null,
    });
  },

  toggleFamily(family) {
    const current = get().families;
    const families = current.includes(family)
      ? current.filter((f) => f !== family)
      : [...current, family];

    if (families.length === 0) {
      set({ ...INITIAL });
      return;
    }

    set({
      mode: "lens",
      direction: "downstream",
      routeFrom: null,
      routeTo: null,
      routePicking: false,
      families,
      tourStep: null,
    });
  },

  setLens(input) {
    const families = Array.from(new Set(input));

    if (families.length === 0) {
      set({ ...INITIAL });
      return;
    }

    set({
      mode: "lens",
      direction: "downstream",
      routeFrom: null,
      routeTo: null,
      routePicking: false,
      families,
      tourStep: null,
    });
  },

  reset() {
    set({ ...INITIAL });
  },
}));
