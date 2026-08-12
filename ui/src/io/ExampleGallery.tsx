// Starter gallery shown on an empty canvas -- lets a new user open a bundled example instead
// of staring at a blank grid. Renders nothing once the canvas has any nodes.

import { useEffect } from "react";

import { X } from "lucide-react";

import type { Graph } from "../generated/ir";
import { useGraphStore } from "../store/graphStore";
import { useFlowStore } from "./flowStore";

export function ExampleGallery({
  onClose,
}: {
  onClose: () => void;
}): JSX.Element | null {
  const examples = useFlowStore((s) => s.examples);

  useEffect(() => {
    useFlowStore.getState().fetchExamples();
  }, []);

  if (examples.length === 0) return null;

  async function handleOpen(path: string) {
    try {
      const graph = await useFlowStore.getState().loadExample(path);
      useGraphStore.getState().loadIR(graph as Graph);
    } catch {
      // loadExample already sets error on the flow store
    }
  }

  return (
    <div
      style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        zIndex: 5,
        maxWidth: 720,
        width: "90%",
      }}
    >
      <div
        className="glass"
        style={{
          padding: "var(--space-5)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "var(--space-2)",
          }}
        >
          <div>
            <h2
              style={{
                fontSize: "var(--text-xl)",
                fontWeight: 600,
                margin: 0,
                color: "var(--text-primary)",
              }}
            >
              Get started
            </h2>
            <p
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--text-secondary)",
                margin: "var(--space-1) 0 0",
              }}
            >
              Open an example to explore, or start from scratch.
            </p>
          </div>
          <button
            type="button"
            aria-label="Close"
            data-testid="gallery-close"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--text-secondary)",
              padding: "var(--space-1)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <X size={16} />
          </button>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: "var(--space-3)",
          }}
        >
          {examples.map((ex) => (
            <button
              key={ex.path}
              onClick={() => handleOpen(ex.path)}
              data-testid={`example-${ex.slug}`}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-1)",
                padding: "var(--space-3)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                background: "var(--surface-2)",
                cursor: "pointer",
                textAlign: "left",
                transition: "border-color var(--motion-fast) var(--motion-ease)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor =
                  "var(--border-subtle)";
              }}
            >
              <span
                style={{
                  fontSize: "var(--text-sm)",
                  fontWeight: 500,
                  color: "var(--text-primary)",
                }}
              >
                {ex.name}
              </span>
              <span
                style={{
                  fontSize: "var(--text-xs)",
                  color: "var(--text-tertiary)",
                }}
              >
                Open a copy
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
