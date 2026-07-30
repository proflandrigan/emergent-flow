import { expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { FAMILY } from "../theme/family";
import { SECTIONS, groupNodesBySection } from "./Palette";

const catalogFamilies = [
  ...new Set((catalog.nodes as CatalogNode[]).map((n) => n.family)),
];

function node(type: string, family: string, label?: string): CatalogNode {
  return {
    type,
    version: 1,
    family,
    label: label ?? type,
    paradigm: "functional",
    ports: [],
    params: [],
  };
}

test("every family in the shipped catalog is claimed by a SECTIONS entry", () => {
  const claimed = new Set<string>(SECTIONS.flatMap((s) => [...s.families]));
  expect(catalogFamilies.filter((f) => !claimed.has(f))).toEqual([]);
});

test("every family in the shipped catalog has a themed label and hue", () => {
  expect(catalogFamilies.filter((f) => !(f in FAMILY))).toEqual([]);
});

test("no catalog node falls through to the 'more' section", () => {
  const result = groupNodesBySection(catalog.nodes as CatalogNode[]);
  expect(result.find((s) => s.id === "more")).toBeUndefined();
});

test("family listed in SECTIONS groups its nodes under the correct section", () => {
  const nodes = [
    node("data.load_csv", "data"),
    node("data.load_json", "data"),
    node("stats.describe", "stats"),
  ];
  const result = groupNodesBySection(nodes);
  const data = result.find((s) => s.id === "data")!;
  expect(data).toBeDefined();
  const dataFamily = data.families.find((f) => f.family === "data")!;
  expect(dataFamily).toBeDefined();
  expect(dataFamily.nodes).toHaveLength(2);
  expect(dataFamily.nodes[0].type).toBe("data.load_csv");
  expect(dataFamily.nodes[1].type).toBe("data.load_json");

  const analyze = result.find((s) => s.id === "analyze")!;
  const statsFamily = analyze.families.find((f) => f.family === "stats")!;
  expect(statsFamily).toBeDefined();
  expect(statsFamily.nodes).toHaveLength(1);
  expect(statsFamily.nodes[0].type).toBe("stats.describe");
});

test("sections are ordered as the ML workflow reads top-to-bottom", () => {
  expect(SECTIONS.map((s) => s.id)).toEqual([
    "data",
    "prepare",
    "explore",
    "analyze",
    "model",
    "explain",
    "ai",
    "report",
    "utility",
  ]);
});

test("family NOT listed in any SECTIONS entry ends up in a trailing 'more' section", () => {
  const nodes = [
    node("custom.widget", "custom"),
    node("custom.chart", "custom"),
  ];
  const result = groupNodesBySection(nodes);
  const more = result.find((s) => s.id === "more")!;
  expect(more).toBeDefined();
  expect(more.label).toBe("More");
  expect(result[result.length - 1].id).toBe("more");
  const customFamily = more.families.find((f) => f.family === "custom")!;
  expect(customFamily).toBeDefined();
  expect(customFamily.nodes).toHaveLength(2);
});

test("'more' families are ordered by display label, not by node insertion order", () => {
  // Input is sorted by node label (as the palette sorts it), which would put
  // `zeta` first if the fallback followed insertion order.
  const nodes = [
    node("zeta.alpha", "zeta", "Alpha"),
    node("alpha.beta", "alpha", "Beta"),
    node("mid.gamma", "mid", "Gamma"),
  ];
  const more = groupNodesBySection(nodes).find((s) => s.id === "more")!;
  expect(more.families.map((f) => f.family)).toEqual(["alpha", "mid", "zeta"]);
});

test("SECTIONS family with zero matching nodes produces an empty families array for that section", () => {
  const nodes = [node("ml.train", "ml")];
  const result = groupNodesBySection(nodes);
  const data = result.find((s) => s.id === "data")!;
  expect(data.families).toHaveLength(0);
  const analyze = result.find((s) => s.id === "analyze")!;
  expect(analyze.families).toHaveLength(0);
  const model = result.find((s) => s.id === "model")!;
  expect(model.families).toHaveLength(1);
  expect(model.families[0].family).toBe("ml");
});

test("when there are no leftover families, no 'more' section is present", () => {
  const nodes = [
    node("data.load_csv", "data"),
    node("stats.describe", "stats"),
    node("ml.train", "ml"),
  ];
  const result = groupNodesBySection(nodes);
  const more = result.find((s) => s.id === "more");
  expect(more).toBeUndefined();
});

test("node order within a family group is preserved from the input array", () => {
  const nodes = [
    node("z_last", "data", "Z last"),
    node("a_first", "data", "A first"),
    node("m_middle", "data", "M middle"),
  ];
  const result = groupNodesBySection(nodes);
  const data = result.find((s) => s.id === "data")!;
  const dataFamily = data.families.find((f) => f.family === "data")!;
  expect(dataFamily.nodes).toHaveLength(3);
  expect(dataFamily.nodes[0].type).toBe("z_last");
  expect(dataFamily.nodes[1].type).toBe("a_first");
  expect(dataFamily.nodes[2].type).toBe("m_middle");
});
