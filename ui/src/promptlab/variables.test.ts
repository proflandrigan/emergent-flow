import { describe, expect, test } from "vitest";

import {
  extractVariables,
  extractVariablesFromTemplates,
  splitTemplateSegments,
} from "./variables";

describe("extractVariables", () => {
  test("finds a single variable", () => {
    expect(extractVariables("Hello {{name}}")).toEqual(["name"]);
  });

  test("dedupes repeats in first-appearance order", () => {
    expect(extractVariables("{{a}} and {{a}} and {{b}}")).toEqual(["a", "b"]);
  });

  test("tolerates internal whitespace", () => {
    expect(extractVariables("{{ spaced }}")).toEqual(["spaced"]);
  });

  test("returns [] for a template with no variables", () => {
    expect(extractVariables("no variables here")).toEqual([]);
  });
});

describe("extractVariablesFromTemplates", () => {
  test("merges and dedupes across two templates", () => {
    expect(
      extractVariablesFromTemplates(["{{a}} {{b}}", "{{b}} {{c}}"]),
    ).toEqual(["a", "b", "c"]);
  });
});

describe("splitTemplateSegments", () => {
  test("splits text and variable segments", () => {
    expect(splitTemplateSegments("Hi {{name}}!")).toEqual([
      { kind: "text", value: "Hi " },
      { kind: "var", value: "name" },
      { kind: "text", value: "!" },
    ]);
  });

  test("returns a single text segment when there are no variables", () => {
    expect(splitTemplateSegments("no variables here")).toEqual([
      { kind: "text", value: "no variables here" },
    ]);
  });
});
