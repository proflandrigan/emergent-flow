export const VAR_PATTERN = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;

// Every distinct {{var}} name referenced in `template`, in first-appearance order.
export function extractVariables(template: string): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const match of template.matchAll(VAR_PATTERN)) {
    const name = match[1];
    if (!seen.has(name)) {
      seen.add(name);
      names.push(name);
    }
  }
  return names;
}

// Every distinct {{var}} name across multiple templates (e.g. system + user), deduplicated,
// first-appearance order across the templates in the order given.
export function extractVariablesFromTemplates(templates: string[]): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const template of templates) {
    for (const name of extractVariables(template)) {
      if (!seen.has(name)) {
        seen.add(name);
        names.push(name);
      }
    }
  }
  return names;
}

// Splits `template` into an array of segments for rendering: each segment is either
// `{ kind: "text"; value: string }` or `{ kind: "var"; name: string }` (the {{name}} match,
// without its braces). Concatenating `value`/`{{name}}` back in order reconstructs `template`.
export interface TemplateSegment {
  kind: "text" | "var";
  value: string;
}

export function splitTemplateSegments(template: string): TemplateSegment[] {
  const segments: TemplateSegment[] = [];
  let lastIndex = 0;
  for (const match of template.matchAll(VAR_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push({ kind: "text", value: template.slice(lastIndex, index) });
    }
    segments.push({ kind: "var", value: match[1] });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < template.length) {
    segments.push({ kind: "text", value: template.slice(lastIndex) });
  }
  return segments;
}
