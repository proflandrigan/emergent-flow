// PURE mapping between a catalog param's metadata and the form widget that edits it. No React,
// no DOM, no I/O -- this module only converts between typed IR values and the strings an
// <input>/<select> shows, so it can be unit-tested in isolation. Task 04's ConfigForm consumes
// it; it must stay pure so the form logic itself stays trivially testable.

import type { CatalogParam } from "../catalog/types";

export type WidgetKind = "select" | "checkbox" | "number" | "text" | "list";

// True when the type token is a list/sequence, e.g. "list" or "list[str]".
export function isListType(typeToken: string): boolean {
  return typeToken === "list" || typeToken.startsWith("list[");
}

// Choose the widget. Precedence: explicit choices -> "select"; then by type_token:
//   "bool" -> "checkbox"; "int"|"float" -> "number"; list types -> "list"; otherwise "text".
export function widgetForParam(param: CatalogParam): WidgetKind {
  if (param.hints?.choices) {
    return "select";
  }
  if (param.type_token === "bool") {
    return "checkbox";
  }
  if (param.type_token === "int" || param.type_token === "float") {
    return "number";
  }
  if (isListType(param.type_token)) {
    return "list";
  }
  return "text";
}

// Render a typed IR value as the string an <input>/<select> shows.
//   null/undefined -> ""; list -> array joined with ", "; otherwise String(value).
export function formatValue(param: CatalogParam, value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

// Parse a raw input string back to the typed IR value.
//   "number": Number(raw) (NaN/empty -> null); int token floors? NO -- keep Number() as-is.
//   list: split on ",", trim each, drop empties -> string[] (empty -> []).
//   text/select: the raw string (empty string stays "" -- do NOT coerce to null).
export function parseValue(param: CatalogParam, raw: string): unknown {
  const kind = widgetForParam(param);
  if (kind === "number") {
    if (raw.trim() === "") {
      return null;
    }
    const n = Number(raw);
    return Number.isNaN(n) ? null : n;
  }
  if (kind === "list") {
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  }
  return raw;
}

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") {
    return true;
  }
  return Array.isArray(value) && value.length === 0;
}

// Inline validation against the hints. Returns an error message or null when valid.
// Order: required-empty first, then type-specific.
export function validateValue(
  param: CatalogParam,
  value: unknown,
): string | null {
  const empty = isEmptyValue(value);
  if (param.required && empty) {
    return "Required";
  }
  if (empty) {
    return null;
  }

  const hints = param.hints;
  const kind = widgetForParam(param);

  if (kind === "number") {
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) {
      return "Must be a number";
    }
    if (hints?.min != null && n < hints.min) {
      return `Must be ≥ ${hints.min}`;
    }
    if (hints?.max != null && n > hints.max) {
      return `Must be ≤ ${hints.max}`;
    }
    return null;
  }

  if (kind === "list") {
    // For lists, min_length/max_length bound the number of items (matching the backend's
    // generic length check in nodes/contract.py), not a character count.
    const arr = Array.isArray(value) ? value : [];
    if (hints?.min_length != null && arr.length < hints.min_length) {
      return `Must have at least ${hints.min_length} items`;
    }
    if (hints?.max_length != null && arr.length > hints.max_length) {
      return `Must have at most ${hints.max_length} items`;
    }
    return null;
  }

  // text/select: string value
  const str = typeof value === "string" ? value : String(value);
  if (hints?.min_length != null && str.length < hints.min_length) {
    return `Must be at least ${hints.min_length} characters`;
  }
  if (hints?.max_length != null && str.length > hints.max_length) {
    return `Must be at most ${hints.max_length} characters`;
  }
  if (hints?.pattern) {
    let matches = true;
    try {
      matches = new RegExp(hints.pattern).test(str);
    } catch {
      matches = true;
    }
    if (!matches) {
      return `Does not match ${hints.pattern}`;
    }
  }
  if (hints?.choices && !hints.choices.includes(str)) {
    return `Must be one of: ${hints.choices.join(", ")}`;
  }
  return null;
}
