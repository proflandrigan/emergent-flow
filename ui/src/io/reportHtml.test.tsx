import { describe, expect, test } from "vitest";

import type { Payload } from "../store/execution";
import type { NodeModel } from "../store/model";
import type { Tour } from "../session/sessionClient";
import { buildReportHtml, collectReportCards, describeTourStepAnchors } from "./reportHtml";

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

describe("tours in report", () => {
  const tour: Tour = {
    id: "t1",
    title: "Walkthrough",
    author: "agent",
    conclusion: "CONCLUSION-TEXT",
    steps: [
      { note: "STEP-ONE", focus: ["a", "b"], unknowns: ["Why is x null?"] },
      { note: "STEP-TWO", route: ["a", "c"] },
    ],
  };

  test("tours-only report lists conclusion before steps", () => {
    const html = buildReportHtml({ graphName: "g", cards: [], results: {}, tours: [tour] });
    expect(html).toContain("Guided tours");
    expect(html).toContain("<h3>Walkthrough</h3>");
    expect(html).not.toContain("No result cards");
    expect(html.indexOf("CONCLUSION-TEXT")).toBeLessThan(html.indexOf("STEP-ONE"));
    expect(html.indexOf("STEP-ONE")).toBeLessThan(html.indexOf("STEP-TWO"));
    expect(html).toContain('<ol class="tour-steps">');
    expect(html).toContain("Open questions");
    expect(html).toContain("Why is x null?");
  });

  test("absent tours is identical to empty tours and keeps the placeholder", () => {
    const a = buildReportHtml({ graphName: "g", cards: [], results: {} });
    const b = buildReportHtml({ graphName: "g", cards: [], results: {}, tours: [] });
    expect(a).toBe(b);
    expect(a).toContain("No result cards in this graph.");
  });

  test("escapes hostile strings", () => {
    const evil: Tour = {
      id: "e",
      title: "<script>alert(1)</script>",
      author: '"><img src=x onerror=alert(1)>',
      conclusion: "ok",
      steps: [{ note: "n", focus: ["<b>x</b>"], unknowns: ["<script>"] }],
    };
    const html = buildReportHtml({ graphName: "g", cards: [], results: {}, tours: [evil] });
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<b>x</b>");
    expect(html).toContain("script-src 'none'");
  });

  test("unsafe markdown is neutralised", () => {
    const bad: Tour = {
      id: "m",
      title: "T",
      author: "a",
      conclusion: "c",
      steps: [{ note: "[click](javascript:alert(1))\n\n<iframe src=x></iframe>" }],
    };
    const html = buildReportHtml({ graphName: "g", cards: [], results: {}, tours: [bad] });
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain("<iframe src=x");
  });

  test("describeTourStepAnchors", () => {
    expect(describeTourStepAnchors({ note: "n", focus: ["a", "b"] })).toBe("Focus: a, b");
    expect(describeTourStepAnchors({ note: "n", focus: ["a"], reach: "down" })).toBe(
      "Focus: a (reach down)",
    );
    expect(describeTourStepAnchors({ note: "n", route: ["a", "b"] })).toBe("Route: a \u2192 b");
  });
});
