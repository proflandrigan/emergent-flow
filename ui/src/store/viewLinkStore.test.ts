import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { parseViewHash } from "../io/viewLink";
import { copyViewLink, useViewLinkStore } from "./viewLinkStore";

beforeEach(() => {
  useViewLinkStore.setState({
    pendingCanvas: null,
    pendingProposal: null,
    pendingReview: null,
    notice: null,
    fallbackUrl: null,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  test("splits canvas state from panel targets", () => {
    useViewLinkStore.getState().request(parseViewHash("#focus=n1&reach=up"));
    const s = useViewLinkStore.getState();
    expect(s.pendingCanvas?.focus).toEqual(["n1"]);
    expect(s.pendingCanvas?.reach).toBe("upstream");
    expect(s.pendingProposal).toBeNull();
  });

  test("a proposal-only link leaves pendingCanvas null", () => {
    useViewLinkStore.getState().request(parseViewHash("#proposal=p1"));
    const s = useViewLinkStore.getState();
    expect(s.pendingCanvas).toBeNull();
    expect(s.pendingProposal).toBe("p1");
  });

  test("an empty state is a no-op", () => {
    useViewLinkStore.getState().request(parseViewHash(""));
    const s = useViewLinkStore.getState();
    expect(s.pendingCanvas).toBeNull();
    expect(s.pendingProposal).toBeNull();
    expect(s.pendingReview).toBeNull();
  });
});

describe("consume", () => {
  test("consumeCanvas, consumeProposal, consumeReview null their slot", () => {
    useViewLinkStore.setState({
      pendingCanvas: { focus: ["n1"], reach: null, route: null, lens: [], edge: null },
      pendingProposal: "p1",
      pendingReview: "r1",
    });
    useViewLinkStore.getState().consumeCanvas();
    expect(useViewLinkStore.getState().pendingCanvas).toBeNull();
    useViewLinkStore.getState().consumeProposal();
    expect(useViewLinkStore.getState().pendingProposal).toBeNull();
    useViewLinkStore.getState().consumeReview();
    expect(useViewLinkStore.getState().pendingReview).toBeNull();
  });
});

describe("copyViewLink", () => {
  test("copies to the clipboard and sets a notice", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const url = await copyViewLink({ focus: ["n1"] });
    expect(url.endsWith("#focus=n1")).toBe(true);
    expect(writeText).toHaveBeenCalledWith(url);
    const s = useViewLinkStore.getState();
    expect(s.notice).toBe("Link copied");
    expect(s.fallbackUrl).toBeNull();
  });

  test("falls back to showing the URL when clipboard access is denied", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const url = await copyViewLink({ focus: ["n1"] });
    const s = useViewLinkStore.getState();
    expect(s.fallbackUrl).toBe(url);
    expect(s.notice).toBeNull();
  });

  test("falls back when the Clipboard API is missing", async () => {
    vi.stubGlobal("navigator", {});
    const url = await copyViewLink({ focus: ["n1"] });
    expect(useViewLinkStore.getState().fallbackUrl).toBe(url);
  });
});

describe("addNotice", () => {
  test("appends to an existing notice instead of overwriting it", () => {
    useViewLinkStore.getState().addNotice("a");
    useViewLinkStore.getState().addNotice("b");
    expect(useViewLinkStore.getState().notice).toBe("a; b");
  });
});
