import { describe, expect, test } from "vitest";

import type { Payload } from "../store/execution";
import type { NodeModel } from "../store/model";
import { buildReportHtml, collectReportCards } from "./reportHtml";

function card(
  id: string,
  x: number,
  y: number,
  title?: string,
  blocks: unknown[] = [],
): NodeModel {
  const params = [{ name: "blocks_json", typeToken: "str", value: JSON.stringify(blocks) }];
  if (title !== undefined) {
    params.push({ name: "title", typeToken: "str", value: title });
  }
  return {
    id,
    type: "reports.result_card",
    paradigm: "functional",
    params,
    ports: [],
    position: { x, y },
  };
}

describe("collectReportCards", () => {
  test("sorts by y then x, defaults title, ignores other nodes", () => {
    const other: NodeModel = {
      id: "o",
      type: "data.load",
      paradigm: "functional",
      params: [],
      ports: [],
      position: { x: 0, y: 0 },
    };
    const cards = collectReportCards({
      a: card("a", 50, 100, "B"),
      b: card("b", 10, 100, "A"),
      c: card("c", 0, 200),
      o: other,
    });
    expect(cards.map((c) => c.title)).toEqual(["A", "B", "Results"]);
  });
});

describe("buildReportHtml", () => {
  const blocks = [
    { kind: "markdown", text: "**bold**" },
    { kind: "result", source: "n1:out", caption: "cap" },
    { kind: "result", source: "n2:out", caption: "" },
  ];
  const results: Record<string, Record<string, Payload>> = {
    n1: { out: { kind: "scalar", value: 12345 } },
  };

  test("renders title, markdown, payload and pending message", () => {
    const cards = collectReportCards({ a: card("a", 0, 0, "My Card", blocks) });
    const html = buildReportHtml({ graphName: "g", cards, results });
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("<h2>My Card</h2>");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("12345");
    expect(html).toContain('<p class="caption">cap</p>');
    expect(html).toContain("No result available (graph not run).");
  });

  test("empty graph shows placeholder", () => {
    const html = buildReportHtml({ graphName: "g", cards: [], results: {} });
    expect(html).toContain("No result cards in this graph.");
  });

  test("escapes user text", () => {
    const evil = "<script>alert(1)</script>";
    const cards = collectReportCards({
      a: card("a", 0, 0, evil, [{ kind: "result", source: "x:y", caption: evil }]),
    });
    const html = buildReportHtml({ graphName: evil, cards, results: {} });
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });

  test("html payloads are rendered in a script-less sandboxed iframe", () => {
    const cards = collectReportCards({
      a: card("a", 0, 0, "T", [{ kind: "result", source: "n1:h", caption: "" }]),
    });
    const html = buildReportHtml({
      graphName: "g",
      cards,
      results: { n1: { h: { kind: "html", value: "<script>alert(1)</script>" } as Payload } },
    });
    expect(html).toContain('sandbox=""');
    expect(html).not.toContain("allow-scripts");
    expect(html).not.toContain("<script>");
  });
});
