// Header controls for the flow-aware toolbar: a "File" menu (New/Open/Save/Save As/Rename/
// Export/Import), an editable flow name bound to Graph.name, a dirty indicator, and the
// tidy-layout button. Export/import still route through `serializeIR`/`parseImport`
// (`./irFile.ts`); everything flow-persistence-related routes through `useFlowStore`.

import { useEffect, useRef, useState } from "react";

import type { Graph } from "../generated/ir";
import { useGraphStore } from "../store/graphStore";
import { parseImport, serializeIR } from "./irFile";
import { useFlowStore } from "./flowStore";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { Menu, type MenuItem } from "../ui/Menu";

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

// Local, dependency-free slug -- only used to turn a display name into a URL-safe flow slug
// for `renameFlow`. `saveNewFlow`/the server own slug generation for brand-new flows.
function slugify(input: string): string {
  const slug = input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-+|-+$)/g, "");
  return slug || "flow";
}

export function IRToolbar(): JSX.Element {
  const [error, setError] = useState<string | null>(null);
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const [openPanelOpen, setOpenPanelOpen] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const fileMenuRef = useRef<HTMLDivElement | null>(null);

  const name = useGraphStore((s) => s.name);
  const currentSlug = useFlowStore((s) => s.currentSlug);
  const isDirty = useFlowStore((s) => s.isDirty);
  const flows = useFlowStore((s) => s.flows);
  const flowError = useFlowStore((s) => s.error);

  // Close both popovers on outside click / Escape -- mirrors App.tsx's overflow-menu pattern,
  // including the setTimeout-deferred click listener so the click that opened the menu doesn't
  // immediately close it again.
  useEffect(() => {
    if (!fileMenuOpen && !openPanelOpen) {
      return undefined;
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setFileMenuOpen(false);
        setOpenPanelOpen(false);
      }
    }
    function onClick(e: MouseEvent) {
      if (
        fileMenuRef.current &&
        !fileMenuRef.current.contains(e.target as Node)
      ) {
        setFileMenuOpen(false);
        setOpenPanelOpen(false);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    const timer = window.setTimeout(() => {
      document.addEventListener("click", onClick);
    }, 0);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(timer);
      document.removeEventListener("click", onClick);
    };
  }, [fileMenuOpen, openPanelOpen]);

  function dismissError() {
    setError(null);
    useFlowStore.getState().clearError();
  }

  function handleExport() {
    const graph = useGraphStore.getState().toIR();
    const json = serializeIR(graph);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    const filename = slugify(useGraphStore.getState().name || "graph");
    anchor.download = `${filename}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setFileMenuOpen(false);
  }

  function handleImportClick() {
    setFileMenuOpen(false);
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

  function handleNew() {
    setFileMenuOpen(false);
    if (
      useFlowStore.getState().isDirty &&
      !window.confirm("Discard unsaved changes?")
    ) {
      return;
    }
    useGraphStore.getState().reset();
    useFlowStore.getState().setCurrentSlug(null);
    useFlowStore.getState().setDirty(false);
  }

  function handleOpenToggle() {
    setFileMenuOpen(false);
    setOpenPanelOpen((open) => !open);
    useFlowStore.getState().fetchFlows();
  }

  async function handleOpenFlow(slug: string) {
    try {
      const graph = await useFlowStore.getState().loadFlow(slug);
      // loadFlow() already set isDirty: false, but loadIR() below replaces
      // graphStore's nodes/edges/name -- startDirtyTracking's subscriber (App.tsx) sees
      // those refs change and flips isDirty back to true, which would show the "unsaved
      // changes" indicator on a freshly-opened, unmodified flow. Reassert clean afterward,
      // the same way handleNew() does after reset().
      useGraphStore.getState().loadIR(graph as Graph);
      useFlowStore.getState().setDirty(false);
      setOpenPanelOpen(false);
    } catch {
      // Surfaced via flowStore.error -- nothing else to do here.
    }
  }

  async function handleDeleteFlow(slug: string, e: React.MouseEvent) {
    e.stopPropagation();
    await useFlowStore.getState().deleteFlow(slug);
  }

  async function handleSaveAs() {
    setFileMenuOpen(false);
    const proposed = useGraphStore.getState().name || "Untitled";
    const input = window.prompt("Save flow as:", proposed);
    if (!input || !input.trim()) {
      return;
    }
    const trimmed = input.trim();
    useGraphStore.getState().setName(trimmed);
    const graph = useGraphStore.getState().toIR();
    try {
      await useFlowStore.getState().saveNewFlow(trimmed, graph);
    } catch {
      // Surfaced via flowStore.error -- nothing else to do here.
    }
  }

  async function handleSave() {
    setFileMenuOpen(false);
    const slug = useFlowStore.getState().currentSlug;
    if (!slug) {
      await handleSaveAs();
      return;
    }
    const graph = useGraphStore.getState().toIR();
    await useFlowStore.getState().saveFlow(slug, graph);
  }

  async function handleRename() {
    setFileMenuOpen(false);
    const slug = useFlowStore.getState().currentSlug;
    if (!slug) {
      return;
    }
    const proposed = useGraphStore.getState().name || "";
    const input = window.prompt("Rename flow:", proposed);
    if (!input || !input.trim()) {
      return;
    }
    const trimmed = input.trim();
    const newSlug = slugify(trimmed);
    try {
      await useFlowStore.getState().renameFlow(slug, newSlug);
    } catch {
      // Surfaced via flowStore.error. Renaming failed server-side (e.g. a slug conflict) --
      // don't rename the in-memory graph, that would desync the displayed name from what's
      // actually saved under the old slug.
      return;
    }
    useGraphStore.getState().setName(trimmed);
    // The server's rename() only moves the file (old slug -> new slug); it never rewrites the
    // "name" field inside the graph JSON. Without this save, the flow list (which reads `name`
    // straight from each file) would keep showing the pre-rename name forever. Persist the
    // updated name under the new slug so the on-disk copy and the in-memory graph agree.
    const graph = useGraphStore.getState().toIR();
    await useFlowStore.getState().saveFlow(newSlug, graph);
  }

  function startEditingName() {
    setNameDraft(useGraphStore.getState().name || "");
    setEditingName(true);
  }

  function commitName() {
    setEditingName(false);
    const trimmed = nameDraft.trim();
    useGraphStore.getState().setName(trimmed);
    const slug = useFlowStore.getState().currentSlug;
    if (slug) {
      const graph = useGraphStore.getState().toIR();
      useFlowStore.getState().saveFlow(slug, graph);
    }
  }

  const fileMenuItems: MenuItem[] = [
    { label: "New", onSelect: handleNew, testId: "file-menu-new" },
    { label: "Open…", onSelect: handleOpenToggle, testId: "file-menu-open" },
    { label: "Save    ⌘S", onSelect: handleSave, testId: "file-menu-save" },
    { label: "Save As…", onSelect: handleSaveAs, testId: "file-menu-save-as" },
    {
      label: "Rename…",
      onSelect: handleRename,
      disabled: !currentSlug,
      testId: "file-menu-rename",
    },
    { label: "Export JSON", onSelect: handleExport, testId: "file-menu-export" },
    {
      label: "Import JSON",
      onSelect: handleImportClick,
      testId: "file-menu-import",
    },
  ];

  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: "var(--space-1)",
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--space-2)",
        }}
      >
        <div ref={fileMenuRef} style={{ position: "relative" }}>
          <Button
            variant="ghost"
            data-testid="file-menu-toggle"
            onClick={() => {
              setOpenPanelOpen(false);
              setFileMenuOpen((open) => !open);
            }}
          >
            File
          </Button>
          {fileMenuOpen && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                marginTop: "var(--space-1)",
                zIndex: 20,
              }}
            >
              <Menu items={fileMenuItems} aria-label="File" />
            </div>
          )}
          {openPanelOpen && (
            <div
              className="glass"
              data-testid="open-flow-panel"
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                marginTop: "var(--space-1)",
                zIndex: 20,
                width: 260,
                maxHeight: 320,
                overflow: "auto",
                padding: "var(--space-2)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "var(--space-2)",
                }}
              >
                <span
                  style={{
                    fontSize: "var(--text-sm)",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  Saved flows
                </span>
                <IconButton
                  aria-label="Close"
                  onClick={() => setOpenPanelOpen(false)}
                >
                  ×
                </IconButton>
              </div>
              {flows.length === 0 ? (
                <div
                  style={{
                    fontSize: "var(--text-sm)",
                    color: "var(--text-secondary)",
                  }}
                >
                  No saved flows yet.
                </div>
              ) : (
                <ul
                  style={{
                    listStyle: "none",
                    margin: 0,
                    padding: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-1)",
                  }}
                >
                  {flows.map((flow) => (
                    <li
                      key={flow.slug}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "var(--space-2)",
                      }}
                    >
                      <button
                        type="button"
                        data-testid={`open-flow-${flow.slug}`}
                        onClick={() => handleOpenFlow(flow.slug)}
                        style={{
                          flex: 1,
                          textAlign: "left",
                          background: "transparent",
                          border: "none",
                          color: "var(--text-primary)",
                          fontSize: "var(--text-sm)",
                          padding: "var(--space-1) var(--space-2)",
                          borderRadius: "var(--radius-sm)",
                          cursor: "pointer",
                        }}
                      >
                        {flow.name}
                      </button>
                      <IconButton
                        aria-label={`Delete ${flow.name}`}
                        data-testid={`delete-flow-${flow.slug}`}
                        onClick={(e) => handleDeleteFlow(flow.slug, e)}
                      >
                        ×
                      </IconButton>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <Button
          variant="ghost"
          data-testid="tidy-layout"
          onClick={handleTidyLayout}
        >
          Tidy layout
        </Button>

        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
          }}
        >
          {editingName ? (
            <input
              autoFocus
              value={nameDraft}
              data-testid="flow-name-input"
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={commitName}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitName();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setEditingName(false);
                }
              }}
              style={{
                fontSize: "var(--text-sm)",
                padding: "2px 6px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-subtle)",
                background: "var(--surface)",
                color: "var(--text-primary)",
                width: 160,
              }}
            />
          ) : (
            <span
              data-testid="flow-name"
              onClick={startEditingName}
              title="Click to rename"
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--text-secondary)",
                cursor: "text",
                maxWidth: 180,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                display: "inline-block",
              }}
            >
              {name || "Untitled"}
            </span>
          )}
          {isDirty && (
            <span
              aria-hidden="true"
              data-testid="dirty-indicator"
              title="Unsaved changes"
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--warning)",
                display: "inline-block",
                flexShrink: 0,
              }}
            />
          )}
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          data-testid="ir-file"
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
      </div>
      {(error || flowError) && (
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
          <span>{error || flowError}</span>
          <IconButton aria-label="Dismiss" onClick={dismissError}>
            ×
          </IconButton>
        </div>
      )}
    </div>
  );
}
