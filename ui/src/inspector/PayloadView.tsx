// Renders a single execution `Payload` (a tagged union returned by `/execute`) minimally and
// readably. Rich tables/charts are roadmap Epic 8 -- this is deliberately raw output. PURE
// presentational component: no store access, no fetch, props in / JSX out.

import type { CSSProperties } from "react";

import type { Payload } from "../store/execution";

const mutedStyle: CSSProperties = { color: "#666" };

const preStyle: CSSProperties = { whiteSpace: "pre-wrap", margin: 0 };

const tableStyle: CSSProperties = {
  fontSize: 11,
  borderCollapse: "collapse",
};

const cellStyle: CSSProperties = {
  border: "1px solid #ccc",
  padding: "0.15rem 0.4rem",
};

export function PayloadView({
  payload,
}: {
  payload: Payload;
}): JSX.Element | null {
  switch (payload.kind) {
    case "scalar": {
      const { value } = payload;
      if (value === null) {
        return (
          <span data-testid="payload-scalar" style={mutedStyle}>
            null
          </span>
        );
      }
      const text =
        typeof value === "boolean" ? (value ? "true" : "false") : String(value);
      return <span data-testid="payload-scalar">{text}</span>;
    }

    case "text":
      return (
        <pre data-testid="payload-text" style={preStyle}>
          {payload.value}
          {payload.truncated ? (
            <span style={mutedStyle}> (truncated, {payload.length} chars)</span>
          ) : null}
        </pre>
      );

    case "table": {
      const [rows, cols] = payload.shape;
      return (
        <table data-testid="payload-table" style={tableStyle}>
          <caption style={{ ...mutedStyle, textAlign: "left" }}>
            {rows} × {cols}
            {payload.truncated ? " (truncated)" : ""}
          </caption>
          <thead>
            <tr>
              {payload.columns.map((col) => (
                <th key={col} style={cellStyle}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {payload.head.map((row, i) => (
              <tr key={i}>
                {payload.columns.map((col) => (
                  <td key={col} style={cellStyle}>
                    {String(row[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    case "record":
      return (
        <div data-testid="payload-record">
          <div style={{ fontWeight: 600 }}>{payload.type}</div>
          {Object.entries(payload.fields).map(([name, field]) => (
            <div key={name} style={{ marginLeft: "0.5rem" }}>
              <span style={{ fontWeight: 600 }}>{name}: </span>
              <PayloadView payload={field} />
            </div>
          ))}
        </div>
      );

    case "json":
      return (
        <pre data-testid="payload-json" style={preStyle}>
          {JSON.stringify(payload.value, null, 2)}
        </pre>
      );

    case "unsupported":
      return (
        <div data-testid="payload-unsupported" style={mutedStyle}>
          {`<${payload.type}> ${payload.repr}`}
        </div>
      );

    case "image":
      return (
        <img
          data-testid="payload-image"
          src={`data:${payload.mime};base64,${payload.data}`}
          alt="result"
          style={{ maxWidth: "100%", maxHeight: 300 }}
        />
      );

    case "html":
      return (
        <iframe
          data-testid="payload-html"
          title="report"
          srcDoc={payload.value}
          sandbox="allow-scripts"
          style={{ width: "100%", height: 400, border: "none" }}
        />
      );

    default: {
      const _exhaustive: never = payload;
      void _exhaustive;
      return null;
    }
  }
}

export default PayloadView;
