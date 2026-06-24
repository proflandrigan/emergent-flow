// Node palette / search (Epic 5 Story 11): lists the node catalog with a search box; clicking
// an entry adds that node to the canvas via the store (Epic 5 Story 3). Click-to-add only --
// drag-and-drop from the palette is out of scope for v1.

import { useState } from "react";

import { useCatalog } from "../catalog/useCatalog";
import { useGraphStore } from "../store/graphStore";

export function Palette(): JSX.Element {
  const catalog = useCatalog();
  const addNodeFromSpec = useGraphStore((s) => s.addNodeFromSpec);
  const [query, setQuery] = useState("");

  const normalizedQuery = query.trim().toLowerCase();
  const nodes = catalog.nodes
    .filter((node) => {
      if (!normalizedQuery) {
        return true;
      }
      return (
        node.label.toLowerCase().includes(normalizedQuery) ||
        node.type.toLowerCase().includes(normalizedQuery)
      );
    })
    .sort((a, b) => a.label.localeCompare(b.label));

  return (
    <aside
      style={{
        width: 220,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid #ddd",
        height: "100%",
      }}
    >
      <div style={{ padding: "0.5rem" }}>
        <input
          data-testid="palette-search"
          type="text"
          placeholder="Search nodes…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ width: "100%", boxSizing: "border-box" }}
        />
      </div>
      <div
        data-testid="palette-list"
        style={{ flex: 1, minHeight: 0, overflowY: "auto" }}
      >
        {nodes.map((node) => (
          <button
            key={node.type}
            type="button"
            onClick={() => {
              const n = Object.keys(useGraphStore.getState().nodes).length;
              const position = { x: 80 + (n % 8) * 24, y: 80 + (n % 8) * 24 };
              addNodeFromSpec(node, position);
            }}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "0.4rem 0.5rem",
              border: "none",
              borderBottom: "1px solid #eee",
              background: "none",
              cursor: "pointer",
            }}
          >
            <div>{node.label}</div>
            <div style={{ fontSize: "0.75rem", color: "#666" }}>
              {node.family} · {node.type}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
