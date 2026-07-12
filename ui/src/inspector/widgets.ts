// PURE mapping between a catalog param's metadata and the form widget that edits it. No React,
// no DOM, no I/O -- this module only converts between typed IR values and the strings an
// <input>/<select>/<textarea> shows, so it can be unit-tested in isolation. Task 04's ConfigForm
// consumes it; it must stay pure so the form logic itself stays trivially testable.

import type { CatalogParam } from "../catalog/types";

export type WidgetKind = "select" | "checkbox" | "number" | "text" | "list" | "json" | "sql" | "connection" | "column" | "markdown";

// True when the type token is a list/sequence, e.g. "list" or "list[str]".
export function isListType(typeToken: string): boolean {
  return typeToken === "list" || typeToken.startsWith("list[");
}

// True when the type token is a mapping/object, e.g. "dict" or "dict[str, any]".
export function isDictType(typeToken: string): boolean {
  return typeToken === "dict" || typeToken.startsWith("dict[");
}

// True when the type token is a list whose elements are themselves dicts/objects, e.g.
// "list[dict[str, any]]" (ml.pipeline's `steps`). A flat comma-separated "list" widget can't
// represent per-item object structure, so this shape needs the JSON widget instead.
export function isListOfDictType(typeToken: string): boolean {
  return typeToken.startsWith("list[dict") || typeToken.startsWith("list[dict[");
}

// Choose the widget. Precedence: explicit widget hint -> sql/connection/column; then
// choices -> "select"; then by type_token:
//   "bool" -> "checkbox"; "int"|"float" -> "number"; dict types (incl. list-of-dict) -> "json";
//   list types -> "list"; otherwise "text".
export function widgetForParam(param: CatalogParam): WidgetKind {
  if (param.hints?.widget === "sql") {
    return "sql";
  }
  if (param.hints?.widget === "markdown") {
    return "markdown";
  }
  if (param.hints?.widget === "connection") {
    return "connection";
  }
  if (param.hints?.widget === "column") {
    return "column";
  }
  if (param.hints?.choices) {
    return "select";
  }
  if (param.type_token === "bool") {
    return "checkbox";
  }
  if (param.type_token === "int" || param.type_token === "float") {
    return "number";
  }
  if (isDictType(param.type_token) || isListOfDictType(param.type_token)) {
    return "json";
  }
  if (isListType(param.type_token)) {
    return "list";
  }
  return "text";
}

// Render a typed IR value as the string an <input>/<select>/<textarea> shows.
//   null/undefined -> ""; dict -> pretty JSON; list -> array joined with ", "; otherwise
//   String(value).
export function formatValue(param: CatalogParam, value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (widgetForParam(param) === "json" && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

// Parse a raw input string back to the typed IR value.
//   "number": Number(raw) (NaN/empty -> null); int token floors? NO -- keep Number() as-is.
//   list: split on ",", trim each, drop empties -> string[] (empty -> []).
//   json: JSON.parse(raw); invalid JSON is returned as the raw string so validateValue can flag
//     it, rather than silently discarding the user's in-progress edit.
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
  if (kind === "json") {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
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

  if (kind === "list" || (kind === "column" && isListType(param.type_token))) {
    // For lists, min_length/max_length bound the number of items (matching the backend's
    // generic length check in nodes/contract.py), not a character count. A "column" widget
    // backed by a list[str] param (e.g. multi-select feature columns) is length-bounded the
    // same way -- without this branch it would fall through to the text/select case below and
    // stringify the array, checking string length instead of item count.
    const arr = Array.isArray(value) ? value : [];
    if (hints?.min_length != null && arr.length < hints.min_length) {
      return `Must have at least ${hints.min_length} items`;
    }
    if (hints?.max_length != null && arr.length > hints.max_length) {
      return `Must have at most ${hints.max_length} items`;
    }
    return null;
  }

  if (kind === "json") {
    // parseValue returns the raw string itself when JSON.parse fails, so a string value here
    // means the user's last edit was invalid JSON.
    if (typeof value === "string") {
      return "Invalid JSON";
    }
    if (isListOfDictType(param.type_token)) {
      if (!Array.isArray(value)) {
        return "Must be a JSON array";
      }
    } else if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return "Must be a JSON object";
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
