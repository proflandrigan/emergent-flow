import { CodingAgentsSection } from "./CodingAgentsSection";
import { LlmConnectionsSection } from "./LlmConnectionsSection";
import { WarehouseConnectionsSection } from "./WarehouseConnectionsSection";

export function ConnectionManagerPanel(): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <h2
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: 600,
          margin: 0,
          color: "var(--text-primary)",
        }}
      >
        Connections
      </h2>

      <WarehouseConnectionsSection />

      <hr
        style={{
          border: "none",
          borderTop: "1px solid var(--border-subtle)",
          margin: 0,
          width: "100%",
        }}
      />

      <LlmConnectionsSection />

      <hr
        style={{
          border: "none",
          borderTop: "1px solid var(--border-subtle)",
          margin: 0,
          width: "100%",
        }}
      />

      <CodingAgentsSection />
    </div>
  );
}
