// Find-node modal: ⌘K opens a fuzzy search over all nodes on the canvas.
// Select a result to centre the viewport on it and select it.

import { Search } from "lucide-react";
import { useState, useMemo, useCallback, useEffect, useRef, type JSX } from "react";
import { createPortal } from "react-dom";

import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";

export interface FindNodeModalProps {
  onClose: () => void;
  onNavigate: (nodeId: string) => void;
}

interface FlatNode {
  id: string;
  label: string;
  type: string;
  paramValues: string[];
}

function flattenNodes(nodes: Record<string, { id: string; label?: string; type: string; params: { value?: unknown }[] }>): FlatNode[] {
  return Object.values(nodes).map((n) => ({
    id: n.id,
    label: n.label ?? n.type,
    type: n.type,
    paramValues: n.params.map((p) => String(p.value ?? "")),
  }));
}

function scoreMatch(query: string, node: FlatNode): number {
  const q = query.toLowerCase();
  if (node.label.toLowerCase() === q) return 100;
  if (node.label.toLowerCase().startsWith(q)) return 80;
  if (node.label.toLowerCase().includes(q)) return 60;
  if (node.type.toLowerCase().includes(q)) return 40;
  if (node.paramValues.some((v) => v.toLowerCase().includes(q))) return 20;
  return 0;
}

export function FindNodeModal({
  onClose,
  onNavigate,
}: FindNodeModalProps): JSX.Element {
  const [query, setQuery] = useState("");
  const [focusedIndex, setFocusedIndex] = useState(0);
  const nodes = useGraphStore((s) => s.nodes);
  const groupMeta = useGraphStore((s) => s.groupMeta);

  const flatNodes = useMemo(() => {
    const nodeEntries = flattenNodes(nodes);
    const groupEntries: FlatNode[] = [];
    if (groupMeta) {
      for (const [gid, meta] of Object.entries(groupMeta)) {
        groupEntries.push({
          id: gid,
          label: meta.label,
          type: "group",
          paramValues: [],
        });
      }
    }
    return [...nodeEntries, ...groupEntries];
  }, [nodes, groupMeta]);

  const results = useMemo(() => {
    if (!query.trim()) {
      return flatNodes.slice(0, 50);
    }
    const q = query.trim().toLowerCase();
    const scored = flatNodes
      .map((n) => ({ node: n, score: scoreMatch(q, n) }))
      .filter((n) => n.score > 0)
      .sort((a, b) => b.score - a.score);
    return scored.map((s) => s.node).slice(0, 50);
  }, [query, flatNodes]);

  const setNodeSelected = useSelectionStore((s) => s.setNodeSelected);
  const clearSelection = useSelectionStore((s) => s.clear);

  const selectNode = useCallback(
    (nodeId: string) => {
      clearSelection();
      setNodeSelected(nodeId, true);
      onNavigate(nodeId);
      onClose();
    },
    [clearSelection, setNodeSelected, onNavigate, onClose],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && results[focusedIndex]) {
        e.preventDefault();
        selectNode(results[focusedIndex].id);
      }
    },
    [results, focusedIndex, selectNode, onClose],
  );

  const handleKeyDownRef = useRef(handleKeyDown);
  handleKeyDownRef.current = handleKeyDown;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => handleKeyDownRef.current(e);
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    setFocusedIndex(0);
  }, [query]);

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 40,
        display: "flex",
        justifyContent: "center",
        paddingTop: "10vh",
        background: "rgba(0, 0, 0, 0.3)",
      }}
      onClick={onClose}
    >
      <div
        className="glass"
        role="dialog"
        aria-modal="true"
        aria-label="Find node"
        style={{
          width: 420,
          maxHeight: "60vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "var(--space-3)", borderBottom: "1px solid var(--border-subtle)" }}>
          <div className="ef-input-wrapper" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <Search size={14} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
            <input
              type="text"
              placeholder="Search nodes by label, type, or param value…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
              style={{
                flex: 1,
                border: "none",
                background: "none",
                outline: "none",
                color: "var(--text-primary)",
                font: "inherit",
                fontSize: "var(--text-sm)",
              }}
              data-testid="find-node-input"
            />
          </div>
        </div>
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          {results.length === 0 ? (
            <p
              style={{
                padding: "var(--space-4)",
                color: "var(--text-secondary)",
                textAlign: "center",
                fontSize: "var(--text-sm)",
              }}
            >
              {query.trim() ? "No matching nodes found." : "Start typing to search nodes."}
            </p>
          ) : (
            results.map((node, i) => {
              const isFocused = i === focusedIndex;
              const isGroup = node.type === "group";
              const groupColor = isGroup && groupMeta ? groupMeta[node.id]?.color : undefined;
              return (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => selectNode(node.id)}
                  onMouseEnter={() => setFocusedIndex(i)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-2)",
                    width: "100%",
                    padding: "var(--space-2) var(--space-3)",
                    border: "none",
                    background: isFocused ? "var(--surface-2)" : "none",
                    cursor: "pointer",
                    color: "var(--text-primary)",
                    font: "inherit",
                    fontSize: "var(--text-sm)",
                    textAlign: "left",
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                  data-testid={`find-node-result-${i}`}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: isGroup ? 2 : "50%",
                      background: groupColor ?? "var(--text-tertiary)",
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {node.label}
                  </span>
                  <span style={{ color: "var(--text-tertiary)", fontSize: "0.7rem", flexShrink: 0 }}>
                    {node.type}
                  </span>
                </button>
              );
            })
          )}
        </div>
        <div
          style={{
            padding: "var(--space-2) var(--space-3)",
            borderTop: "1px solid var(--border-subtle)",
            color: "var(--text-tertiary)",
            fontSize: "0.65rem",
            display: "flex",
            gap: "var(--space-3)",
          }}
        >
          <span>↑↓ Navigate</span>
          <span>↵ Select</span>
          <span>Esc Close</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
