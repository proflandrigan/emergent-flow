// Renders a `research.build_report` node's `Report` record payload with a proper meta header,
// a readable section index, and the composed HTML in a sandboxed iframe -- rather than the raw
// nested-field dump PayloadView falls back to for other record types. PURE presentational
// component: no store access, no fetch, props in / JSX out.

import type { CSSProperties } from "react";

import type { Payload } from "../store/execution";

const mutedStyle: CSSProperties = { color: "var(--text-secondary)" };

function scalarString(p: Payload | undefined): string | null {
  if (p?.kind === "scalar" && typeof p.value === "string") {
    return p.value;
  }
  return null;
}

function isRecordPayload(
  p: Payload | undefined,
): p is Extract<Payload, { kind: "record" }> {
  return p?.kind === "record";
}

function sectionEntryTitle(entry: unknown): string | null {
  if (typeof entry !== "object" || entry === null) {
    return null;
  }
  if (!("title" in entry)) {
    return null;
  }
  const { title } = entry;
  return typeof title === "string" ? title : null;
}

function reportHtml(field: Payload | undefined): string | null {
  if (field?.kind === "html") {
    return field.value;
  }
  if (field?.kind === "scalar" && typeof field.value === "string" && field.value.startsWith("<")) {
    return field.value;
  }
  if (field?.kind === "text" && field.value.startsWith("<")) {
    return field.value;
  }
  return null;
}

export function ReportView({
  payload,
}: {
  payload: Extract<Payload, { kind: "record" }>;
}): JSX.Element {
  const metaField = payload.fields.meta;
  const meta = isRecordPayload(metaField) ? metaField.fields : undefined;
  const title = scalarString(meta?.title) ?? "Report";
  const author = scalarString(meta?.author);
  const generatedAt = scalarString(meta?.generated_at);
  const description = scalarString(meta?.description);

  const bylineParts = [author, generatedAt].filter(
    (v): v is string => v !== null,
  );

  // NOTE: today's server ALWAYS sends `sections` as `{kind: "unsupported"}` -- `Report.sections`
  // is a `list[Section]` of dataclasses, and `emergentflow/server/payload.py::to_payload` cannot
  // `json.dumps` that, so it degrades to a Python repr. The `"json"` branch below is therefore
  // forward-compatible handling, not the live path: it only lights up if the payload contract
  // later gains a way to serialize a list of records. Until then every real Report renders the
  // fallback message. Do not "simplify" this by deleting the branch -- and do not read the
  // `unsupported` repr to fake an index, which would put a Python repr in front of the user.
  const sectionsField = payload.fields.sections;
  const sectionEntries =
    sectionsField?.kind === "json" && Array.isArray(sectionsField.value)
      ? sectionsField.value
      : null;

  const pdfField = payload.fields.pdf_bytes;
  const showPdfNote =
    pdfField !== undefined && !(pdfField.kind === "scalar" && pdfField.value === null);

  const html = reportHtml(payload.fields.html);

  return (
    <div data-testid="payload-report">
      <h3 data-testid="report-title">{title}</h3>
      {bylineParts.length > 0 ? (
        <div data-testid="report-byline" style={mutedStyle}>
          {bylineParts.join(" · ")}
        </div>
      ) : null}
      {description !== null ? (
        <p data-testid="report-description">{description}</p>
      ) : null}
      <div data-testid="report-sections">
        {sectionEntries ? (
          <>
            <div>{sectionEntries.length} sections</div>
            <ul>
              {sectionEntries.map((entry, i) => {
                const entryTitle = sectionEntryTitle(entry);
                return entryTitle !== null ? <li key={i}>{entryTitle}</li> : null;
              })}
            </ul>
          </>
        ) : (
          <span style={mutedStyle}>
            Section detail is not JSON-serializable — see the rendered report below.
          </span>
        )}
      </div>
      {showPdfNote ? (
        <div data-testid="report-pdf-note" style={mutedStyle}>
          PDF rendered (not previewable here).
        </div>
      ) : null}
      {html !== null ? (
        <iframe
          data-testid="report-html"
          title="Rendered report"
          srcDoc={html}
          sandbox="allow-scripts"
          style={{ width: "100%", height: 400, border: "none" }}
        />
      ) : (
        <div data-testid="report-html-empty" style={mutedStyle}>
          No rendered HTML in this report.
        </div>
      )}
    </div>
  );
}
