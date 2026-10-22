// Pure parser/formatter for the canvas deep-link URL hash (issue #168).
// The hash carries view state only and is never written into the graph IR
// (ADR 0014). It is untrusted input, so parsing is defensive and never throws.
import type { TraceDirection } from "../canvas/trace";

export interface ViewRoute {
  from: string;
  to: string;
}

export interface ViewState {
  focus: string[];
  reach: TraceDirection | null;
  route: ViewRoute | null;
  lens: string[];
  edge: string | null;
  proposal: string | null;
  review: string | null;
}

export const EMPTY_VIEW_STATE: ViewState = {
  focus: [],
  reach: null,
  route: null,
  lens: [],
  edge: null,
  proposal: null,
  review: null,
};

export function isEmptyViewState(state: ViewState): boolean {
  return (
    state.focus.length === 0 &&
    state.reach === null &&
    state.route === null &&
    state.lens.length === 0 &&
    state.edge === null &&
    state.proposal === null &&
    state.review === null
  );
}

function safeDecode(s: string): string | null {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
}

function encodeId(id: string): string {
  // Match Python's urllib.parse.quote(safe=""): also escape ! ' ( ) * and ~ (a delimiter here).
  return encodeURIComponent(id).replace(
    /[!'()*~]/g,
    (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0"),
  );
}

function decodeList(raw: string, sep: string): string[] {
  const out: string[] = [];
  for (const part of raw.split(sep)) {
    const decoded = safeDecode(part);
    if (decoded && !out.includes(decoded)) out.push(decoded);
  }
  return out;
}

function decodeOne(raw: string): string | null {
  const decoded = safeDecode(raw);
  return decoded ? decoded : null;
}

function parseReach(raw: string): TraceDirection | null {
  switch (raw.toLowerCase()) {
    case "up":
    case "upstream":
      return "upstream";
    case "down":
    case "downstream":
      return "downstream";
    case "both":
      return "both";
    default:
      return null;
  }
}

export function parseViewHash(hash: string): ViewState {
  const state: ViewState = {
    ...EMPTY_VIEW_STATE,
    focus: [],
    lens: [],
  };
  const body = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!body) return state;

  const params = new Map<string, string>();
  for (const part of body.split("&")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const value = part.slice(idx + 1);
    if (!value) continue;
    params.set(part.slice(0, idx), value);
  }

  const focus = params.get("focus");
  if (focus !== undefined) state.focus = decodeList(focus, ",");

  const reach = params.get("reach");
  if (reach !== undefined) state.reach = parseReach(reach);

  const route = params.get("route");
  if (route !== undefined) {
    const parts = route.split("~").map((p) => safeDecode(p));
    if (parts.length === 2 && parts[0] && parts[1]) {
      state.route = { from: parts[0], to: parts[1] };
    }
  }

  const lens = params.get("lens");
  if (lens !== undefined) state.lens = decodeList(lens, "~");

  const edge = params.get("edge");
  if (edge !== undefined) state.edge = decodeOne(edge);
  const proposal = params.get("proposal");
  if (proposal !== undefined) state.proposal = decodeOne(proposal);
  const review = params.get("review");
  if (review !== undefined) state.review = decodeOne(review);

  return state;
}

export function formatViewHash(state: Partial<ViewState>): string {
  const parts: string[] = [];
  if (state.focus && state.focus.length > 0) {
    parts.push(`focus=${state.focus.map(encodeId).join(",")}`);
  }
  if (state.reach) {
    const short =
      state.reach === "upstream" ? "up" : state.reach === "downstream" ? "down" : "both";
    parts.push(`reach=${short}`);
  }
  if (state.route) {
    parts.push(`route=${encodeId(state.route.from)}~${encodeId(state.route.to)}`);
  }
  if (state.lens && state.lens.length > 0) {
    parts.push(`lens=${state.lens.map(encodeId).join("~")}`);
  }
  if (state.edge) parts.push(`edge=${encodeId(state.edge)}`);
  if (state.proposal) parts.push(`proposal=${encodeId(state.proposal)}`);
  if (state.review) parts.push(`review=${encodeId(state.review)}`);
  return parts.length > 0 ? `#${parts.join("&")}` : "";
}

export function buildViewUrl(
  state: Partial<ViewState>,
  location: { origin: string; pathname: string; search: string } = window.location,
): string {
  return `${location.origin}${location.pathname}${location.search}${formatViewHash(state)}`;
}
