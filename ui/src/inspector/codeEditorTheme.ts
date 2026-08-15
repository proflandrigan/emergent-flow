import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";
import type { Extension } from "@codemirror/state";
import type { Theme } from "../theme/useTheme";

const chrome = EditorView.theme({
  "&": {
    backgroundColor: "var(--surface-1)",
    color: "var(--text-primary)",
    fontSize: "var(--text-sm)",
  },
  ".cm-content": {
    fontFamily: "var(--font-mono)",
    caretColor: "var(--accent)",
  },
  ".cm-gutters": {
    backgroundColor: "var(--surface-2)",
    color: "var(--text-secondary)",
    border: "none",
    borderRight: "1px solid var(--border-subtle)",
  },
  ".cm-activeLine": {
    backgroundColor: "var(--surface-2)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "var(--surface-2)",
  },
  "&.cm-focused": {
    outline: "1px solid var(--border-strong)",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "var(--accent-soft) !important",
  },
});

const darkHighlight = HighlightStyle.define([
  { tag: t.keyword, color: "#c792ea" },
  { tag: [t.string, t.special(t.string)], color: "#c3e88d" },
  { tag: t.comment, color: "#697098", fontStyle: "italic" },
  { tag: [t.number, t.bool, t.null], color: "#f78c6c" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "#82aaff" },
  { tag: t.operator, color: "#89ddff" },
  { tag: t.variableName, color: "var(--text-primary)" },
  { tag: t.propertyName, color: "#82aaff" },
  { tag: t.name, color: "var(--text-primary)" },
]);

const lightHighlight = HighlightStyle.define([
  { tag: t.keyword, color: "#9c27b0" },
  { tag: [t.string, t.special(t.string)], color: "#2e7d32" },
  { tag: t.comment, color: "#8a8a8a", fontStyle: "italic" },
  { tag: [t.number, t.bool, t.null], color: "#c2410c" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "#1565c0" },
  { tag: t.operator, color: "#00838f" },
  { tag: t.variableName, color: "var(--text-primary)" },
  { tag: t.propertyName, color: "#1565c0" },
  { tag: t.name, color: "var(--text-primary)" },
]);

export function codeEditorExtensions(theme: Theme): Extension[] {
  return [chrome, syntaxHighlighting(theme === "light" ? lightHighlight : darkHighlight)];
}
