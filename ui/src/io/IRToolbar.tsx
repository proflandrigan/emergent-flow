// Header controls for IR JSON import/export (Story 5). Export serializes the current canvas
// straight from the store; import parses + validates (via `parseImport`) and surfaces a
// first-class error banner instead of silently failing on bad/old/new graphs.

import { useRef, useState } from "react";

import { useGraphStore } from "../store/graphStore";
import { parseImport, serializeIR } from "./irFile";

// Read a File's text via FileReader rather than file.text(): the latter is unimplemented in
// jsdom (the test env), while FileReader works in jsdom and every browser.
function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () =>
      reject(reader.error ?? new Error("failed to read file"));
    reader.readAsText(file);
  });
}

export function IRToolbar(): JSX.Element {
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function handleExport() {
    const graph = useGraphStore.getState().toIR();
    const json = serializeIR(graph);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "graph.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function handleImportClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset now so re-selecting the same file still fires `change`.
    e.target.value = "";
    if (!file) {
      return;
    }
    const text = await readFileText(file);
    const res = parseImport(text);
    if (res.graph) {
      useGraphStore.getState().loadIR(res.graph);
      setError(null);
    } else {
      setError(res.error ?? "Import failed");
    }
  }

  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: "0.25rem",
      }}
    >
      <div style={{ display: "inline-flex", gap: "0.5rem" }}>
        <button type="button" data-testid="ir-export" onClick={handleExport}>
          Export
        </button>
        <button
          type="button"
          data-testid="ir-import"
          onClick={handleImportClick}
        >
          Import
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          data-testid="ir-file"
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
      </div>
      {error && (
        <div role="alert" data-testid="ir-error" style={{ color: "#c00" }}>
          {error}
          <button type="button" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}
    </div>
  );
}
