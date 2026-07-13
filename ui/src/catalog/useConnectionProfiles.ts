// Fetch the local connection-profile list from the server. There is no committed static
// fallback (unlike the node catalog) — connection profiles are local/per-user, never checked
// into the repo — so the fallback is simply an empty list until the server responds.
//
// The server's GET /connections returns BOTH warehouse and LLM profiles in one list, tagged by a
// "kind" field. useConnectionProfiles() (this hook, zero args) filters to warehouse profiles
// only — its return type and behavior predate the LLM kind and every existing caller
// (SchemaBrowserPanel, ConnectionManagerPanel) assumes warehouse-only data. useLlmConnectionProfiles()
// is the separate, parallel hook for the new LLM kind.

import { useEffect, useState } from "react";

export interface ConnectionProfileSummary {
  kind: "warehouse";
  name: string;
  dialect: string;
  coordinates: Record<string, string>;
  auth_method: string;
  credential_refs: Record<string, string>;
  limits: Record<string, number>;
  write_enabled: boolean;
}

export interface LlmConnectionProfileSummary {
  kind: "llm";
  name: string;
  provider: string;
  api_key_env: string;
  base_url_env?: string | null;
  default_model?: string | null;
}

interface RawConnectionsResponse {
  connections: Array<Record<string, unknown>>;
}

export function useConnectionProfiles(): ConnectionProfileSummary[] {
  const [profiles, setProfiles] = useState<ConnectionProfileSummary[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch("/connections")
      .then((res) => res.json() as Promise<RawConnectionsResponse>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.connections)) {
          const warehouseOnly = data.connections.filter(
            (p) => p.kind === "warehouse" || p.kind === undefined,
          ) as unknown as ConnectionProfileSummary[];
          setProfiles(warehouseOnly);
        }
      })
      .catch(() => {
        /* keep the empty fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return profiles;
}

export function useLlmConnectionProfiles(): LlmConnectionProfileSummary[] {
  const [profiles, setProfiles] = useState<LlmConnectionProfileSummary[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch("/connections")
      .then((res) => res.json() as Promise<RawConnectionsResponse>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.connections)) {
          const llmOnly = data.connections.filter(
            (p) => p.kind === "llm",
          ) as unknown as LlmConnectionProfileSummary[];
          setProfiles(llmOnly);
        }
      })
      .catch(() => {
        /* keep the empty fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return profiles;
}
