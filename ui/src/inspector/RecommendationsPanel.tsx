// Renders `recommend.recommend` / `recommend.similar_items` results as per-user ranked
// cards instead of the generic table. The payload is a tidy DataFrame with columns
// `user_id`, `item_id`, `rank`, `score`. PURE presentational component: no store access,
// props in / JSX out. Falls back to the generic `PayloadView` table when the columns
// don't match the expected recommendation shape.

import type { CSSProperties } from "react";

import type { Payload } from "../store/execution";
import { PayloadView } from "./PayloadView";

const REQUIRED_COLUMNS = ["user_id", "item_id", "rank", "score"];

const cardStyle: CSSProperties = {
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-sm)",
  padding: "var(--space-2)",
  marginBottom: "var(--space-2)",
};

const userStyle: CSSProperties = {
  fontWeight: 600,
  fontSize: "var(--text-sm)",
  marginBottom: "var(--space-1)",
};

const listStyle: CSSProperties = {
  margin: 0,
  paddingLeft: "1.25rem",
  fontSize: "var(--text-sm)",
};

const scoreStyle: CSSProperties = { color: "var(--text-secondary)" };

export function isRecommendationPayload(
  payload: Payload,
): payload is Extract<Payload, { kind: "table" }> {
  return (
    payload.kind === "table" &&
    REQUIRED_COLUMNS.every((col) => payload.columns.includes(col))
  );
}

export function RecommendationsPanel({
  payload,
}: {
  payload: Extract<Payload, { kind: "table" }>;
}): JSX.Element {
  if (!isRecommendationPayload(payload)) {
    return <PayloadView payload={payload} />;
  }

  // Group rows by user_id, preserving first-seen order.
  const byUser = new Map<string, typeof payload.head>();
  for (const row of payload.head) {
    const key = String(row.user_id);
    const rows = byUser.get(key) ?? [];
    rows.push(row);
    byUser.set(key, rows);
  }

  return (
    <div data-testid="recommendations-panel">
      {[...byUser.entries()].map(([userId, rows]) => {
        const sorted = [...rows].sort(
          (a, b) => Number(a.rank) - Number(b.rank),
        );
        return (
          <div key={userId} data-testid="recommendation-user" style={cardStyle}>
            <div style={userStyle}>User {userId}</div>
            <ol style={listStyle}>
              {sorted.map((row, i) => (
                <li key={i}>
                  {String(row.item_id)}{" "}
                  <span style={scoreStyle}>({String(row.score)})</span>
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </div>
  );
}

export default RecommendationsPanel;
