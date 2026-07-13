import { render, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import {
  useConnectionProfiles,
  useLlmConnectionProfiles,
} from "./useConnectionProfiles";

const MIXED_RESPONSE = {
  connections: [
    {
      kind: "warehouse",
      name: "my_pg",
      dialect: "postgresql",
      coordinates: { host: "localhost", port: 5432, database: "mydb" },
      auth_method: "password",
      credential_refs: {},
      limits: {},
      write_enabled: false,
    },
    {
      kind: "llm",
      name: "my_anthropic",
      provider: "anthropic",
      api_key_env: "ANTHROPIC_API_KEY",
      default_model: "claude-sonnet-5",
    },
    {
      kind: "warehouse",
      name: "analytics",
      dialect: "bigquery",
      coordinates: { project: "my-project" },
      auth_method: "service_account",
      credential_refs: {},
      limits: {},
      write_enabled: true,
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
});

function WarehouseHost() {
  const profiles = useConnectionProfiles();
  return (
    <div>
      {profiles.map((p) => (
        <span key={p.name} data-testid="profile">
          {p.name} ({p.dialect})
        </span>
      ))}
    </div>
  );
}

function LlmHost() {
  const profiles = useLlmConnectionProfiles();
  return (
    <div>
      {profiles.map((p) => (
        <span key={p.name} data-testid="profile">
          {p.name} ({p.provider})
        </span>
      ))}
    </div>
  );
}

test("useConnectionProfiles returns only warehouse entries from a mixed response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(MIXED_RESPONSE), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  const { container } = render(<WarehouseHost />);

  await waitFor(() => {
    const items = container.querySelectorAll('[data-testid="profile"]');
    expect(items.length).toBe(2);
    expect(items[0]).toHaveTextContent("my_pg (postgresql)");
    expect(items[1]).toHaveTextContent("analytics (bigquery)");
  });
});

test("useLlmConnectionProfiles returns only llm entries from a mixed response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(MIXED_RESPONSE), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  const { container } = render(<LlmHost />);

  await waitFor(() => {
    const items = container.querySelectorAll('[data-testid="profile"]');
    expect(items.length).toBe(1);
    expect(items[0]).toHaveTextContent("my_anthropic (anthropic)");
  });
});

test("both hooks return empty array on fetch rejection (network error)", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network error"));

  function DualHost() {
    const warehouse = useConnectionProfiles();
    const llm = useLlmConnectionProfiles();
    return (
      <div>
        <span data-testid="warehouse-count">{warehouse.length}</span>
        <span data-testid="llm-count">{llm.length}</span>
      </div>
    );
  }

  const { container } = render(<DualHost />);

  await waitFor(() => {
    expect(container.querySelector('[data-testid="warehouse-count"]')).toHaveTextContent("0");
    expect(container.querySelector('[data-testid="llm-count"]')).toHaveTextContent("0");
  });
});
