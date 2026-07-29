import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Payload } from "../store/execution";
import { PayloadView } from "./PayloadView";
import { ReportView } from "./ReportView";

type ReportPayload = Extract<Payload, { kind: "record" }>;

function makeReportPayload(
  overrides: Record<string, Payload> = {},
): ReportPayload {
  return {
    kind: "record",
    type: "Report",
    fields: {
      meta: {
        kind: "record",
        type: "ReportMeta",
        fields: {
          title: { kind: "scalar", value: "My Report" },
          author: { kind: "scalar", value: "jl" },
          generated_at: { kind: "scalar", value: "2026-01-01" },
          description: { kind: "scalar", value: "d" },
        },
      },
      sections: {
        kind: "unsupported",
        type: "list",
        repr:
          "[Section(kind='markdown', title='Intro', content='hello'), Section(kind='table', title='T', content=   a\n0  1)]",
      },
      html: {
        kind: "html",
        value: "<!doctype html><html><body>hello-report-marker</body></html>",
        truncated: false,
      },
      pdf_bytes: { kind: "scalar", value: null },
      ...overrides,
    },
  };
}

test("renders the report title and byline from meta", () => {
  const payload = makeReportPayload();
  render(<ReportView payload={payload} />);
  expect(screen.getByTestId("report-title")).toHaveTextContent("My Report");
  const byline = screen.getByTestId("report-byline");
  expect(byline).toHaveTextContent("jl");
  expect(byline).toHaveTextContent("2026-01-01");
});

test("omits the byline when author and generated_at are both null", () => {
  const payload = makeReportPayload({
    meta: {
      kind: "record",
      type: "ReportMeta",
      fields: {
        title: { kind: "scalar", value: "My Report" },
        author: { kind: "scalar", value: null },
        generated_at: { kind: "scalar", value: null },
        description: { kind: "scalar", value: "d" },
      },
    },
  });
  render(<ReportView payload={payload} />);
  expect(screen.queryByTestId("report-byline")).toBeNull();
});

test("omits the description when it is null", () => {
  const payload = makeReportPayload({
    meta: {
      kind: "record",
      type: "ReportMeta",
      fields: {
        title: { kind: "scalar", value: "My Report" },
        author: { kind: "scalar", value: "jl" },
        generated_at: { kind: "scalar", value: "2026-01-01" },
        description: { kind: "scalar", value: null },
      },
    },
  });
  render(<ReportView payload={payload} />);
  expect(screen.queryByTestId("report-description")).toBeNull();
});

test("renders the composed html in a sandboxed iframe", () => {
  const payload = makeReportPayload();
  render(<ReportView payload={payload} />);
  const frame = screen.getByTestId("report-html");
  expect(frame.getAttribute("srcdoc")).toContain("hello-report-marker");
  expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
});

test("does not leak the unsupported sections repr", () => {
  const payload = makeReportPayload();
  render(<ReportView payload={payload} />);
  expect(screen.queryByText(/Section\(kind=/)).toBeNull();
  const sections = screen.getByTestId("report-sections");
  expect(sections).toHaveTextContent(
    "Section detail is not JSON-serializable — see the rendered report below.",
  );
});

test("renders a section index when sections arrive as json", () => {
  const payload = makeReportPayload({
    sections: {
      kind: "json",
      value: [{ title: "Intro" }, { title: "Results" }],
    },
  });
  render(<ReportView payload={payload} />);
  const sections = screen.getByTestId("report-sections");
  expect(sections).toHaveTextContent("Intro");
  expect(sections).toHaveTextContent("Results");
  expect(sections).toHaveTextContent("2");
});

test("shows a pdf note only when pdf bytes are present", () => {
  const withoutPdf = makeReportPayload();
  const { rerender } = render(<ReportView payload={withoutPdf} />);
  expect(screen.queryByTestId("report-pdf-note")).toBeNull();

  const withPdf = makeReportPayload({
    pdf_bytes: { kind: "unsupported", type: "bytes", repr: "b'%PDF'" },
  });
  rerender(<ReportView payload={withPdf} />);
  const note = screen.getByTestId("report-pdf-note");
  expect(note).toHaveTextContent("PDF rendered (not previewable here).");
  expect(screen.queryByText(/%PDF/)).toBeNull();
});

test("PayloadView dispatches a Report record to ReportView", () => {
  const payload = makeReportPayload();
  render(<PayloadView payload={payload} />);
  expect(screen.getByTestId("payload-report")).toBeInTheDocument();
  expect(screen.queryByTestId("payload-record")).toBeNull();
});
