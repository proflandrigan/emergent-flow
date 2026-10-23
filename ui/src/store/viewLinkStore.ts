// Deep-link view state (issue #168) waiting to be applied by the canvas/App, plus the transient
// toast/clipboard-fallback UI for "Copy link" actions. Ephemeral UI state -- it must NEVER be
// serialized into the IR (ADR 0014: the graph store owns IR data only).

import { create } from "zustand";

import { buildViewUrl, isEmptyViewState, type ViewState } from "../io/viewLink";
import { useSessionStore } from "../session/sessionStore";

/** The canvas half of a view link: what Canvas applies once React Flow is ready. */
export type CanvasViewRequest = Pick<ViewState, "focus" | "reach" | "route" | "lens" | "edge">;

export interface ViewLinkStore {
  /** Canvas-side view waiting to be applied (null when nothing is pending). */
  pendingCanvas: CanvasViewRequest | null;
  /** Proposal / review panel targets waiting for App to open them. */
  pendingProposal: string | null;
  pendingReview: string | null;
  /** Single user-facing message (unknown ids, copied link, ...); null when none. */
  notice: string | null;
  /** URL to show in a select-all text box when clipboard access was denied. */
  fallbackUrl: string | null;
  /** Split a parsed ViewState into the pending slots. An empty state is a no-op. */
  request: (state: ViewState) => void;
  /** Clear pendingCanvas (Canvas calls this once it has applied it). */
  consumeCanvas: () => void;
  consumeProposal: () => void;
  consumeReview: () => void;
  setNotice: (message: string | null) => void;
  /** Like setNotice but appends to a pending notice so simultaneous unknown-id reports survive. */
  addNotice: (message: string) => void;
  setFallbackUrl: (url: string | null) => void;
}

export const useViewLinkStore = create<ViewLinkStore>((set) => ({
  pendingCanvas: null,
  pendingProposal: null,
  pendingReview: null,
  notice: null,
  fallbackUrl: null,

  request(state) {
    if (isEmptyViewState(state)) return;
    const hasCanvas =
      state.focus.length > 0 ||
      state.reach !== null ||
      state.route !== null ||
      state.lens.length > 0 ||
      state.edge !== null;
    set({
      pendingCanvas: hasCanvas
        ? {
            focus: state.focus,
            reach: state.reach,
            route: state.route,
            lens: state.lens,
            edge: state.edge,
          }
        : null,
      pendingProposal: state.proposal,
      pendingReview: state.review,
    });
  },

  consumeCanvas() {
    set({ pendingCanvas: null });
  },

  consumeProposal() {
    set({ pendingProposal: null });
  },

  consumeReview() {
    set({ pendingReview: null });
  },

  setNotice(message) {
    set({ notice: message });
  },

  addNotice(message) {
    set((s) => ({ notice: s.notice && s.notice !== message ? `${s.notice}; ${message}` : message }));
  },

  setFallbackUrl(url) {
    set({ fallbackUrl: url });
  },
}));

/**
 * Copy a link to `state` (the current origin/path, ?session= of the ACTIVE session -- not the
 * possibly stale one in the address bar -- plus the view hash). Falls back to showing the URL in
 * a select-all box when the Clipboard API is missing or denied. Resolves to the URL.
 */
export async function copyViewLink(state: Partial<ViewState>): Promise<string> {
  const url = buildViewUrl(state, window.location, useSessionStore.getState().sessionId);
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(url);
    useViewLinkStore.getState().setNotice("Link copied");
  } catch {
    useViewLinkStore.getState().setFallbackUrl(url);
  }
  return url;
}
