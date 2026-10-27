import { describe, expect, test } from "vitest";

import {
  formatRunEvidence,
  parseBlocks,
  resolveBlockState,
  serializeBlocks,
  shortRunId,
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

describe("resolveBlockState", () => {
  const block: Extract<ResultCardBlock, { kind: "result" }> = {
    kind: "result",
    source: "n1:out",
    caption: "",
  };
  const meta = { runId: "2026-07-30T14-02-11Z-ab12", finishedAt: "2026-07-30T14:02:11+00:00" };

  test("ok when a payload exists, carrying run identity", () => {
    const r = resolveBlockState(
      block,
      { n1: { out: { kind: "scalar", value: 1 } } },
      { n1: { status: "ok" } },
      meta,
    );
    expect(r).toMatchObject({ state: "ok", nodeId: "n1", port: "out", ...meta });
  });

  test("failed when the source errored without a payload", () => {
    expect(resolveBlockState(block, {}, { n1: { status: "error", error: "x" } }, meta).state).toBe(
      "failed",
    );
  });

  test("unrun when missing, skipped, or the source is malformed", () => {
    expect(resolveBlockState(block, {}, {}, null).state).toBe("unrun");
    expect(resolveBlockState(block, {}, { n1: { status: "skipped" } }, null).state).toBe("unrun");
    const bad = resolveBlockState({ ...block, source: "nocolon" }, {}, {}, null);
    expect(bad.state).toBe("unrun");
    expect(bad.runId).toBeNull();
  });

  test("shortRunId and formatRunEvidence", () => {
    expect(shortRunId(meta.runId)).toBe("ab12");
    expect(shortRunId("abcdefghijkl")).toBe("abcdefgh");
    expect(shortRunId(null)).toBe("");
    expect(formatRunEvidence(meta.runId, meta.finishedAt)).toBe(
      "Run ab12 \u00b7 2026-07-30T14:02:11+00:00",
    );
    expect(formatRunEvidence(meta.runId, meta.finishedAt, true)).toBe(
      "Run 2026-07-30T14-02-11Z-ab12 \u00b7 2026-07-30T14:02:11+00:00",
    );
    expect(formatRunEvidence(null, "2026-01-01T00:00:00+00:00")).toBe(
      "Run \u00b7 2026-01-01T00:00:00+00:00",
    );
    expect(formatRunEvidence(null, null)).toBe("");
  });
});
