import { describe, expect, test } from "vitest";

import {
  parseBlocks,
  serializeBlocks,
  splitSource,
  type ResultCardBlock,
} from "./resultCardBlocks";

describe("resultCardBlocks", () => {
  test("round-trips blocks", () => {
    const blocks: ResultCardBlock[] = [
      { kind: "markdown", text: "# Hi" },
      { kind: "result", source: "n1:out", caption: "Cap" },
    ];
    expect(parseBlocks(serializeBlocks(blocks))).toEqual(blocks);
  });

  test("malformed or non-array input yields []", () => {
    expect(parseBlocks("{not json")).toEqual([]);
    expect(parseBlocks('{"kind":"markdown"}')).toEqual([]);
    expect(parseBlocks(42)).toEqual([]);
    expect(parseBlocks(null)).toEqual([]);
  });

  test("drops invalid entries and defaults caption", () => {
    const json = JSON.stringify([
      { kind: "markdown", text: 5 },
      { kind: "result" },
      { kind: "other" },
      null,
      "str",
      { kind: "result", source: "a:b" },
      { kind: "markdown", text: "ok" },
    ]);
    expect(parseBlocks(json)).toEqual([
      { kind: "result", source: "a:b", caption: "" },
      { kind: "markdown", text: "ok" },
    ]);
  });

  test("splitSource", () => {
    expect(splitSource("a:b")).toEqual({ nodeId: "a", port: "b" });
    expect(splitSource("a:b:c")).toEqual({ nodeId: "a:b", port: "c" });
    expect(splitSource("nocolon")).toBeNull();
    expect(splitSource(":b")).toBeNull();
    expect(splitSource("a:")).toBeNull();
  });
});
