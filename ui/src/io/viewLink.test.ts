import { describe, expect, test } from "vitest";
import {
  EMPTY_VIEW_STATE,
  buildViewUrl,
  formatViewHash,
  isEmptyViewState,
  parseViewHash,
  type ViewState,
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
    };
    expect(parseViewHash(formatViewHash(state))).toEqual(state);
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
});

describe("formatViewHash encoding parity with Python quote", () => {
  test("escapes ! ' ( ) * and ~", () => {
    expect(formatViewHash({ focus: ["a!b'c(d)e*f~g"] })).toBe(
      "#focus=a%21b%27c%28d%29e%2Af%7Eg",
    );
  });
});
