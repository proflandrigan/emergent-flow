import { expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { groupNodesBySection } from "./Palette";

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

test("family listed in SECTIONS groups its nodes under the correct section", () => {
  const nodes = [
    node("data.load_csv", "data"),
    node("data.load_json", "data"),
    node("stats.describe", "stats"),
  ];
  const result = groupNodesBySection(nodes);
  const dataPrep = result.find((s) => s.id === "data-prep")!;
  expect(dataPrep).toBeDefined();
  const dataFamily = dataPrep.families.find((f) => f.family === "data")!;
  expect(dataFamily).toBeDefined();
  expect(dataFamily.nodes).toHaveLength(2);
  expect(dataFamily.nodes[0].type).toBe("data.load_csv");
  expect(dataFamily.nodes[1].type).toBe("data.load_json");

  const analysis = result.find((s) => s.id === "analysis")!;
  const statsFamily = analysis.families.find((f) => f.family === "stats")!;
  expect(statsFamily).toBeDefined();
  expect(statsFamily.nodes).toHaveLength(1);
  expect(statsFamily.nodes[0].type).toBe("stats.describe");
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
  const customFamily = more.families.find((f) => f.family === "custom")!;
  expect(customFamily).toBeDefined();
  expect(customFamily.nodes).toHaveLength(2);
});

test("SECTIONS family with zero matching nodes produces an empty families array for that section", () => {
  const nodes = [node("ml.train", "ml")];
  const result = groupNodesBySection(nodes);
  const dataPrep = result.find((s) => s.id === "data-prep")!;
  expect(dataPrep.families).toHaveLength(0);
  const analysis = result.find((s) => s.id === "analysis")!;
  expect(analysis.families).toHaveLength(0);
  const modeling = result.find((s) => s.id === "modeling")!;
  expect(modeling.families).toHaveLength(1);
  expect(modeling.families[0].family).toBe("ml");
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
  const dataPrep = result.find((s) => s.id === "data-prep")!;
  const dataFamily = dataPrep.families.find((f) => f.family === "data")!;
  expect(dataFamily.nodes).toHaveLength(3);
  expect(dataFamily.nodes[0].type).toBe("z_last");
  expect(dataFamily.nodes[1].type).toBe("a_first");
  expect(dataFamily.nodes[2].type).toBe("m_middle");
});
