// Header controls for IR JSON import/export (Story 5). Export serializes the current canvas
// straight from the store; import parses + validates (via `parseImport`) and surfaces a
// first-class error banner instead of silently failing on bad/old/new graphs.

import { useRef, useState } from "react";

import { useGraphStore } from "../store/graphStore";
import { parseImport, serializeIR } from "./irFile";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";

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

  function handleTidyLayout() {
    useGraphStore.getState().tidyLayout();
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset now so re-selecting the same file still fires `change`.
    e.target.value = "";
    if (!file) {
      return;
    }
    let text: string;
    try {
      text = await readFileText(file);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Could not read file: ${msg}`);
      return;
    }
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
        gap: "var(--space-1)",
      }}
    >
      <div style={{ display: "inline-flex", gap: "var(--space-2)" }}>
        <Button variant="ghost" data-testid="ir-export" onClick={handleExport}>
          Export
        </Button>
        <Button
          variant="ghost"
          data-testid="ir-import"
          onClick={handleImportClick}
        >
          Import
        </Button>
        <Button
          variant="ghost"
          data-testid="tidy-layout"
          onClick={handleTidyLayout}
        >
          Tidy layout
        </Button>
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
        <div
          role="alert"
          data-testid="ir-error"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-sm)",
            background: "var(--danger-soft)",
            border: "1px solid var(--danger)",
            color: "var(--danger)",
            fontSize: "var(--text-sm)",
          }}
        >
          <span>{error}</span>
          <IconButton aria-label="Dismiss" onClick={() => setError(null)}>
            ×
          </IconButton>
        </div>
      )}
    </div>
  );
}
