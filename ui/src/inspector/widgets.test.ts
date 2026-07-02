import { describe, expect, test } from "vitest";

import type { CatalogParam } from "../catalog/types";
import {
  formatValue,
  isDictType,
  isListOfDictType,
  isListType,
  parseValue,
  validateValue,
  widgetForParam,
} from "./widgets";

function param(overrides: Partial<CatalogParam> = {}): CatalogParam {
  return {
    name: "p",
    type_token: "str",
    ...overrides,
  };
}

describe("isListType", () => {
  test("true for list[str]", () => {
    expect(isListType("list[str]")).toBe(true);
  });

  test("true for bare list", () => {
    expect(isListType("list")).toBe(true);
  });

  test("false for str", () => {
    expect(isListType("str")).toBe(false);
  });
});

describe("widgetForParam", () => {
  test("choices win over type_token", () => {
    const p = param({
      type_token: "str",
      hints: { choices: ["mean", "median"] },
    });
    expect(widgetForParam(p)).toBe("select");
  });

  test("bool -> checkbox", () => {
    expect(widgetForParam(param({ type_token: "bool" }))).toBe("checkbox");
  });

  test("int -> number", () => {
    expect(widgetForParam(param({ type_token: "int" }))).toBe("number");
  });

  test("float -> number", () => {
    expect(widgetForParam(param({ type_token: "float" }))).toBe("number");
  });

  test("list[str] -> list", () => {
    expect(widgetForParam(param({ type_token: "list[str]" }))).toBe("list");
  });

  test("str -> text", () => {
    expect(widgetForParam(param({ type_token: "str" }))).toBe("text");
  });
});

describe("formatValue", () => {
  test("list param joins with comma-space", () => {
    const p = param({ type_token: "list[str]" });
    expect(formatValue(p, ["a", "b"])).toBe("a, b");
  });

  test("null becomes empty string", () => {
    expect(formatValue(param(), null)).toBe("");
  });

  test("undefined becomes empty string", () => {
    expect(formatValue(param(), undefined)).toBe("");
  });

  test("number becomes its string form", () => {
    expect(formatValue(param({ type_token: "int" }), 5)).toBe("5");
  });
});

describe("parseValue", () => {
  test("list param splits, trims, drops empties", () => {
    const p = param({ type_token: "list[str]" });
    expect(parseValue(p, "a, b ,")).toEqual(["a", "b"]);
  });

  test("empty list input -> empty array", () => {
    const p = param({ type_token: "list[str]" });
    expect(parseValue(p, "")).toEqual([]);
  });

  test("float parses to number", () => {
    const p = param({ type_token: "float" });
    expect(parseValue(p, "3.5")).toBe(3.5);
  });

  test("empty number input -> null", () => {
    const p = param({ type_token: "int" });
    expect(parseValue(p, "")).toBeNull();
  });

  test("non-numeric number input -> null", () => {
    const p = param({ type_token: "int" });
    expect(parseValue(p, "abc")).toBeNull();
  });

  test("empty text input stays empty string", () => {
    const p = param({ type_token: "str" });
    expect(parseValue(p, "")).toBe("");
  });
});

describe("validateValue", () => {
  test("required + empty -> Required", () => {
    const p = param({ required: true });
    expect(validateValue(p, "")).toBe("Required");
  });

  test("required + empty array -> Required", () => {
    const p = param({ type_token: "list[str]", required: true });
    expect(validateValue(p, [])).toBe("Required");
  });

  test("not required + empty -> null", () => {
    const p = param({ required: false });
    expect(validateValue(p, "")).toBeNull();
  });

  test("number below min -> message", () => {
    const p = param({ type_token: "int", hints: { min: 10 } });
    expect(validateValue(p, 5)).toBe("Must be ≥ 10");
  });

  test("number above max -> message", () => {
    const p = param({ type_token: "int", hints: { max: 10 } });
    expect(validateValue(p, 15)).toBe("Must be ≤ 10");
  });

  test("non-finite number -> Must be a number", () => {
    const p = param({ type_token: "int" });
    expect(validateValue(p, NaN)).toBe("Must be a number");
  });

  test("string failing pattern -> message", () => {
    const p = param({ hints: { pattern: "^[a-z]+$" } });
    expect(validateValue(p, "ABC")).toBe("Does not match ^[a-z]+$");
  });

  test("value in choices -> null", () => {
    const p = param({ hints: { choices: ["mean", "median"] } });
    expect(validateValue(p, "mean")).toBeNull();
  });

  test("value not in choices -> message", () => {
    const p = param({ hints: { choices: ["mean", "median"] } });
    expect(validateValue(p, "mode")).toBe("Must be one of: mean, median");
  });

  test("bad/uncompilable pattern does not throw and is treated as no check", () => {
    const p = param({ hints: { pattern: "(unclosed" } });
    expect(() => validateValue(p, "anything")).not.toThrow();
    expect(validateValue(p, "anything")).toBeNull();
  });

  test("list length below min_length -> message", () => {
    const p = param({ type_token: "list[str]", hints: { min_length: 2 } });
    expect(validateValue(p, ["a"])).toBe("Must have at least 2 items");
  });

  test("list length above max_length -> message", () => {
    const p = param({ type_token: "list[str]", hints: { max_length: 1 } });
    expect(validateValue(p, ["a", "b"])).toBe("Must have at most 1 items");
  });

  test("string shorter than min_length -> message", () => {
    const p = param({ hints: { min_length: 5 } });
    expect(validateValue(p, "abc")).toBe("Must be at least 5 characters");
  });

  test("string longer than max_length -> message", () => {
    const p = param({ hints: { max_length: 2 } });
    expect(validateValue(p, "abc")).toBe("Must be at most 2 characters");
  });
});

describe("isDictType", () => {
  test("true for dict[str, any]", () => {
    expect(isDictType("dict[str, any]")).toBe(true);
  });

  test("true for bare dict", () => {
    expect(isDictType("dict")).toBe(true);
  });

  test("false for str", () => {
    expect(isDictType("str")).toBe(false);
  });
});

describe("widgetForParam - json", () => {
  test("dict[str, any] -> json", () => {
    expect(widgetForParam(param({ type_token: "dict[str, any]" }))).toBe("json");
  });
});

describe("formatValue - json", () => {
  test("dict param pretty-prints as JSON", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(formatValue(p, { n_estimators: 50 })).toBe(
      JSON.stringify({ n_estimators: 50 }, null, 2),
    );
  });

  test("empty dict formats as '{}'", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(formatValue(p, {})).toBe("{}");
  });
});

describe("parseValue - json", () => {
  test("valid JSON object parses to an object", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(parseValue(p, '{"k": 1}')).toEqual({ k: 1 });
  });

  test("invalid JSON is returned as the raw string", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(parseValue(p, "{not json")).toBe("{not json");
  });
});

describe("validateValue - json", () => {
  test("valid object value -> null", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(validateValue(p, { k: 1 })).toBeNull();
  });

  test("invalid JSON (string value) -> Invalid JSON", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(validateValue(p, "{not json")).toBe("Invalid JSON");
  });

  test("empty object is not treated as empty/required-violating", () => {
    const p = param({ type_token: "dict[str, any]", required: true });
    expect(validateValue(p, {})).toBeNull();
  });

  test("a JSON array where a dict is expected -> message", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(validateValue(p, [1, 2])).toBe("Must be a JSON object");
  });

  test("a JSON scalar where a dict is expected -> message", () => {
    const p = param({ type_token: "dict[str, any]" });
    expect(validateValue(p, 42)).toBe("Must be a JSON object");
  });
});

describe("isListOfDictType", () => {
  test("true for list[dict[str, any]]", () => {
    expect(isListOfDictType("list[dict[str, any]]")).toBe(true);
  });

  test("false for list[str]", () => {
    expect(isListOfDictType("list[str]")).toBe(false);
  });

  test("false for dict[str, any]", () => {
    expect(isListOfDictType("dict[str, any]")).toBe(false);
  });
});

describe("widgetForParam - list of dict", () => {
  test("list[dict[str, any]] -> json, not list", () => {
    expect(widgetForParam(param({ type_token: "list[dict[str, any]]" }))).toBe("json");
  });
});

describe("formatValue - list of dict", () => {
  test("list-of-dict param pretty-prints as JSON, not '[object Object]'", () => {
    const p = param({ type_token: "list[dict[str, any]]" });
    const steps = [{ estimator: "StandardScaler", params: {} }];
    expect(formatValue(p, steps)).toBe(JSON.stringify(steps, null, 2));
  });
});

describe("parseValue - list of dict", () => {
  test("valid JSON array of objects parses to an array of objects", () => {
    const p = param({ type_token: "list[dict[str, any]]" });
    expect(parseValue(p, '[{"estimator": "PCA"}]')).toEqual([{ estimator: "PCA" }]);
  });
});

describe("validateValue - list of dict", () => {
  test("valid array value -> null", () => {
    const p = param({ type_token: "list[dict[str, any]]" });
    expect(validateValue(p, [{ estimator: "PCA" }])).toBeNull();
  });

  test("a JSON object where a list is expected -> message", () => {
    const p = param({ type_token: "list[dict[str, any]]" });
    expect(validateValue(p, { estimator: "PCA" })).toBe("Must be a JSON array");
  });
});
