import { describe, expect, test } from "vitest";
import {
  EMPTY_VIEW_STATE,
  buildViewUrl,
  formatViewHash,
  isEmptyViewState,
  parseViewHash,
  type ViewState,
  withSessionParam,
} from "./viewLink";

describe("parseViewHash", () => {
  test("empty and bare # give the empty state", () => {
    expect(parseViewHash("")).toEqual(EMPTY_VIEW_STATE);
    expect(parseViewHash("#")).toEqual(EMPTY_VIEW_STATE);
    expect(isEmptyViewState(parseViewHash(""))).toBe(true);
    expect(parseViewHash("").focus).not.toBe(EMPTY_VIEW_STATE.focus);
  });

  test("focus parses, de-duplicates, and works without #", () => {
    expect(parseViewHash("#focus=n1").focus).toEqual(["n1"]);
    expect(parseViewHash("focus=a,b,a").focus).toEqual(["a", "b"]);
  });

  test("reach synonyms", () => {
    expect(parseViewHash("#reach=up").reach).toBe("upstream");
    expect(parseViewHash("#reach=UPSTREAM").reach).toBe("upstream");
    expect(parseViewHash("#reach=down").reach).toBe("downstream");
    expect(parseViewHash("#reach=downstream").reach).toBe("downstream");
    expect(parseViewHash("#reach=both").reach).toBe("both");
    expect(parseViewHash("#reach=sideways").reach).toBeNull();
  });

  test("route requires exactly two ids", () => {
    expect(parseViewHash("#route=a~b").route).toEqual({ from: "a", to: "b" });
    expect(parseViewHash("#route=a").route).toBeNull();
    expect(parseViewHash("#route=a~").route).toBeNull();
    expect(parseViewHash("#route=a~b~c").route).toBeNull();
  });

  test("lens", () => {
    expect(parseViewHash("#lens=ml~data").lens).toEqual(["ml", "data"]);
  });

  test("edge, proposal, review", () => {
    const s = parseViewHash("#edge=e1&proposal=p1&review=r1");
    expect(s.edge).toBe("e1");
    expect(s.proposal).toBe("p1");
    expect(s.review).toBe("r1");
  });

  test("ignores unknown keys, parts without =, and malformed percent", () => {
    expect(parseViewHash("#foo=bar&focus=n1").focus).toEqual(["n1"]);
    expect(parseViewHash("#junk&focus=n1").focus).toEqual(["n1"]);
    expect(() => parseViewHash("#focus=%E0%A4%A")).not.toThrow();
    expect(parseViewHash("#focus=%E0%A4%A").focus).toEqual([]);
  });
});

describe("formatViewHash", () => {
  test("empty and ordering", () => {
    expect(formatViewHash({})).toBe("");
    expect(formatViewHash({ focus: ["n1"], reach: "downstream" })).toBe("#focus=n1&reach=down");
  });

  test("round trips awkward ids", () => {
    const weird = ["a b", "x/y", "t~u", "c,d", "e&f", "g=h", "i#j", "café☃"];
    const state: ViewState = {
      focus: weird,
      reach: "both",
      route: { from: "a~b", to: "c,d" },
      lens: ["m l", "d~t"],
      edge: "e&1=2",
      proposal: "p#1",
      review: "r/1",
      tour: null,
      step: null,
    };
    expect(parseViewHash(formatViewHash(state))).toEqual(state);
  });
});

describe("tour links", () => {
  test("tour and step parse", () => {
    const a = parseViewHash("#tour=t1");
    expect(a.tour).toBe("t1");
    expect(a.step).toBeNull();
    expect(parseViewHash("#tour=t1&step=3").step).toBe(3);
  });

  test("step rejects non-integer syntax", () => {
    for (const bad of ["-1", "1.5", "+2", "abc", "1e3"]) {
      expect(parseViewHash(`#tour=t1&step=${bad}`).step).toBeNull();
    }
  });

  test("step alone is ignored and the state stays empty", () => {
    const s = parseViewHash("#step=2");
    expect(s.step).toBeNull();
    expect(isEmptyViewState(s)).toBe(true);
  });

  test("percent-encoded id round-trips", () => {
    expect(formatViewHash({ tour: "a b~c", step: 2 })).toBe("#tour=a%20b%7Ec&step=2");
    const s = parseViewHash("#tour=a%20b%7Ec&step=2");
    expect(s.tour).toBe("a b~c");
    expect(s.step).toBe(2);
  });

  test("step defaults to 0 and follows the Python key order", () => {
    expect(formatViewHash({ tour: "t1" })).toBe("#tour=t1&step=0");
    expect(formatViewHash({ focus: ["n1"], tour: "t1", step: 1 })).toBe("#focus=n1&tour=t1&step=1");
  });
});

describe("buildViewUrl", () => {
  test("preserves search and replaces hash", () => {
    expect(
      buildViewUrl(
        { focus: ["n1"] },
        { origin: "http://127.0.0.1:8765", pathname: "/", search: "?session=s1" },
      ),
    ).toBe("http://127.0.0.1:8765/?session=s1#focus=n1");
  });

  test("an explicit sessionId replaces a stale ?session= and keeps other params", () => {
    const loc = { origin: "http://127.0.0.1:8765", pathname: "/", search: "?a=1&session=old" };
    expect(buildViewUrl({ proposal: "p1" }, loc, "new")).toBe(
      "http://127.0.0.1:8765/?a=1&session=new#proposal=p1",
    );
    expect(buildViewUrl({ proposal: "p1" }, loc, null)).toBe(
      "http://127.0.0.1:8765/?a=1#proposal=p1",
    );
  });
});

describe("withSessionParam", () => {
  test("adds, replaces, encodes and removes the session param", () => {
    expect(withSessionParam("", "s1")).toBe("?session=s1");
    expect(withSessionParam("?session=a", "b c")).toBe("?session=b+c");
    expect(withSessionParam("?session=a", null)).toBe("");
    expect(withSessionParam("?x=1", null)).toBe("?x=1");
  });
});

describe("formatViewHash encoding parity with Python quote", () => {
  test("escapes ! ' ( ) * and ~", () => {
    expect(formatViewHash({ focus: ["a!b'c(d)e*f~g"] })).toBe(
      "#focus=a%21b%27c%28d%29e%2Af%7Eg",
    );
  });
});
