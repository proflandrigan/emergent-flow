// Checkpoint review panel (Task 08): renders the session's checkpoint history so the human can
// inspect every agent edit (kind/author/description/version range) and revert the latest edit.
// Reads checkpoints + current version from useSessionStore -- it never fetches its own copy
// except via the Refresh button. Revert is deliberately conservative: only the latest `edit`
// checkpoint (the one whose resulting_version equals the current session version) offers a
// Revert button, so the UI can't trigger cascading reverts.

import { useState, type JSX } from "react";

import { Button } from "../ui/Button";
import type { Checkpoint } from "./sessionClient";
import { useSessionStore } from "./sessionStore";

function kindLabel(kind: Checkpoint["kind"]): string {
  return kind === "edit" ? "Edit" : "Revert";
}

function CheckpointRow({
  checkpoint,
  isLatestEdit,
}: {
  checkpoint: Checkpoint;
  isLatestEdit: boolean;
}): JSX.Element {
  const [reverting, setReverting] = useState(false);

  const handleRevert = (): void => {
    setReverting(true);
    void useSessionStore
      .getState()
      .revertCheckpoint(checkpoint.id)
      .finally(() => setReverting(false));
  };

  const description =
    checkpoint.description.trim() !== ""
      ? checkpoint.description
      : "Agent edit";

  return (
    <div
      data-testid="checkpoint-row"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.5rem",
        marginBottom: "0.5rem",
        fontSize: "var(--text-xs)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          marginBottom: "0.25rem",
        }}
      >
        <span
          style={{
            fontSize: "var(--text-xs)",
            fontWeight: 600,
            padding: "1px 6px",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface-2)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {kindLabel(checkpoint.kind)}
        </span>
        <span style={{ fontWeight: 600 }}>{checkpoint.author}</span>
        <span style={{ color: "var(--text-secondary)" }}>
          {new Date(checkpoint.timestamp).toLocaleString()}
        </span>
      </div>
      <div style={{ marginBottom: "0.25rem" }}>{description}</div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-2)",
        }}
      >
        <span style={{ color: "var(--text-secondary)" }}>
          v{checkpoint.base_version} &rarr; v{checkpoint.resulting_version}
        </span>
        {isLatestEdit ? (
          <Button
            variant="secondary"
            data-testid={`checkpoint-revert-button-${checkpoint.id}`}
            disabled={reverting}
            onClick={handleRevert}
          >
            {reverting ? "Reverting\u2026" : "Revert"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function CheckpointPanel(): JSX.Element {
  const checkpoints = useSessionStore((s) => s.checkpoints);
  const version = useSessionStore((s) => s.version);
  const listCheckpoints = useSessionStore((s) => s.listCheckpoints);
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = (): void => {
    setRefreshing(true);
    void listCheckpoints().finally(() => setRefreshing(false));
  };

  const sorted = Object.values(checkpoints).sort(
    (a, b) => b.timestamp - a.timestamp,
  );

  return (
    <div
      data-testid="checkpoint-panel"
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "var(--space-2)",
          flexShrink: 0,
        }}
      >
        <div style={{ fontWeight: 600 }}>Checkpoints</div>
        <Button
          variant="secondary"
          data-testid="checkpoint-refresh-button"
          disabled={refreshing}
          onClick={handleRefresh}
        >
          {refreshing ? "Refreshing\u2026" : "Refresh"}
        </Button>
      </div>
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
        }}
      >
        {sorted.length === 0 ? (
          <p style={{ color: "var(--text-secondary)" }}>No checkpoints yet.</p>
        ) : (
          sorted.map((checkpoint) => (
            <CheckpointRow
              key={checkpoint.id}
              checkpoint={checkpoint}
              isLatestEdit={
                checkpoint.kind === "edit" &&
                checkpoint.resulting_version === version
              }
            />
          ))
        )}
      </div>
    </div>
  );
}
