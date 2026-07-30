// Node palette / search (Epic 5 Story 11): lists the node catalog with a search box; clicking
// an entry adds that node to the canvas via the store (Epic 5 Story 3). Click-to-add only --
// drag-and-drop from the palette is out of scope for v1.

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";

import type { CatalogNode } from "../catalog/types";
import { useCatalog } from "../catalog/useCatalog";
import { useGraphStore } from "../store/graphStore";
import { familyMeta } from "../theme/family";
import { Input } from "../ui/Input";

const SECTIONS = [
  { id: "data-prep", label: "Data & Prep", families: ["data", "clean"] },
  { id: "analysis", label: "Analysis", families: ["stats", "reports"] },
  { id: "modeling", label: "Modeling", families: ["ml", "nn"] },
] as const;

export interface FamilyGroup {
  family: string;
  nodes: CatalogNode[];
}

export interface SectionGroup {
  id: string;
  label: string;
  families: FamilyGroup[];
}

export function groupNodesBySection(nodes: CatalogNode[]): SectionGroup[] {
  const familyMap = new Map<string, CatalogNode[]>();
  for (const node of nodes) {
    const bucket = familyMap.get(node.family);
    if (bucket) {
      bucket.push(node);
    } else {
      familyMap.set(node.family, [node]);
    }
  }

  const listedFamilies = new Set<string>();
  for (const section of SECTIONS) {
    for (const family of section.families) {
      listedFamilies.add(family);
    }
  }

  const sections: SectionGroup[] = [];
  for (const section of SECTIONS) {
    const families: FamilyGroup[] = [];
    for (const family of section.families) {
      const nodesInFamily = familyMap.get(family);
      if (nodesInFamily && nodesInFamily.length > 0) {
        families.push({ family, nodes: nodesInFamily });
      }
    }
    sections.push({ id: section.id, label: section.label, families });
  }

  const leftoverFamilies: FamilyGroup[] = [];
  for (const [family, fNodes] of familyMap) {
    if (!listedFamilies.has(family)) {
      leftoverFamilies.push({ family, nodes: fNodes });
    }
  }
  if (leftoverFamilies.length > 0) {
    sections.push({ id: "more", label: "More", families: leftoverFamilies });
  }

  return sections;
}

const COLLAPSE_STORAGE_KEY = "ef-palette-collapsed-families";

function getInitialCollapsedFamilies(): Set<string> {
  try {
    const stored = localStorage.getItem(COLLAPSE_STORAGE_KEY);
    if (stored) {
      return new Set(JSON.parse(stored) as string[]);
    }
  } catch {
    // ignore parse errors
  }
  return new Set();
}

export function Palette(): JSX.Element {
  const catalog = useCatalog();
  const addNodeFromSpec = useGraphStore((s) => s.addNodeFromSpec);
  const [query, setQuery] = useState("");
  const [hoveredType, setHoveredType] = useState<string | null>(null);
  const [collapsedFamilies, setCollapsedFamilies] = useState<Set<string>>(
    getInitialCollapsedFamilies,
  );

  useEffect(() => {
    try {
      localStorage.setItem(
        COLLAPSE_STORAGE_KEY,
        JSON.stringify([...collapsedFamilies]),
      );
    } catch {
      // ignore write errors
    }
  }, [collapsedFamilies]);

  const toggleFamily = (family: string) => {
    setCollapsedFamilies((prev) => {
      const next = new Set(prev);
      if (next.has(family)) {
        next.delete(family);
      } else {
        next.add(family);
      }
      return next;
    });
  };

  const normalizedQuery = query.trim().toLowerCase();
  const isSearching = normalizedQuery.length > 0;
  const filteredNodes = catalog.nodes
    .filter((node) => {
      if (!normalizedQuery) {
        return true;
      }
      return (
        node.label.toLowerCase().includes(normalizedQuery) ||
        node.type.toLowerCase().includes(normalizedQuery) ||
        (node.description ?? "").toLowerCase().includes(normalizedQuery) ||
        (node.keywords ?? []).some((k) =>
          k.toLowerCase().includes(normalizedQuery),
        )
      );
    })
    .sort((a, b) => a.label.localeCompare(b.label));

  const groupedSections = groupNodesBySection(filteredNodes);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "var(--space-2)" }}>
        <Input
          data-testid="palette-search"
          type="text"
          placeholder="Search nodes…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          pill
          leadingIcon={<Search size={14} />}
        />
      </div>
      <div
        data-testid="palette-list"
        style={{ flex: 1, minHeight: 0, overflowY: "auto" }}
      >
        {groupedSections
          .filter((section) => section.families.length > 0)
          .map((section) => (
          <div key={section.id}>
            <div
              style={{
                padding: "var(--space-2) var(--space-3) var(--space-1)",
                fontSize: "0.7rem",
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              {section.label}
            </div>
            {section.families.map((fg) => {
              const meta = familyMeta(fg.family);
              const collapsed = isSearching ? false : collapsedFamilies.has(fg.family);
              const FamIcon = meta.Icon;
              return (
                <div key={fg.family}>
                  <button
                    type="button"
                    onClick={() => toggleFamily(fg.family)}
                    aria-expanded={!collapsed}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      width: "100%",
                      padding: "var(--space-2) var(--space-3)",
                      border: "none",
                      background: "none",
                      cursor: "pointer",
                      color: "var(--text-primary)",
                      font: "inherit",
                      textAlign: "left",
                    }}
                  >
                    {collapsed ? (
                      <ChevronRight size={14} style={{ color: "var(--text-tertiary)" }} />
                    ) : (
                      <ChevronDown size={14} style={{ color: "var(--text-tertiary)" }} />
                    )}
                    <span
                      aria-hidden="true"
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: meta.color,
                        flexShrink: 0,
                      }}
                    />
                    <FamIcon size={14} style={{ color: meta.color, flexShrink: 0 }} />
                    <span style={{ flex: 1 }}>{meta.label}</span>
                    <span style={{ color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                      {fg.nodes.length}
                    </span>
                  </button>
                  {!collapsed &&
                    fg.nodes.map((node) => {
                      const isHovered = hoveredType === node.type;
                      return (
                        <button
                          key={node.type}
                          type="button"
                          title={node.description ?? node.type}
                          aria-label={`${node.label} (${node.type})`}
                          onMouseEnter={() => setHoveredType(node.type)}
                          onMouseLeave={() =>
                            setHoveredType((prev) =>
                              prev === node.type ? null : prev,
                            )
                          }
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
                            borderTop: "none",
                            borderRight: "none",
                            borderBottom: "1px solid var(--border-subtle)",
                            borderLeft: `2px solid ${isHovered ? meta.color : "transparent"}`,
                            background: isHovered ? meta.soft : "none",
                            cursor: "pointer",
                            transition:
                              "background var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease)",
                          }}
                        >
                          <div>{node.label}</div>
                        </button>
                      );
                    })}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
