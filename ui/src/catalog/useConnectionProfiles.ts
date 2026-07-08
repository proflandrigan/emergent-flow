// Fetch the local connection-profile list from the server. There is no committed static
// fallback (unlike the node catalog) — connection profiles are local/per-user, never checked
// into the repo — so the fallback is simply an empty list until the server responds.

import { useEffect, useState } from "react";

export interface ConnectionProfileSummary {
  name: string;
  dialect: string;
  auth_method: string;
}

export function useConnectionProfiles(): ConnectionProfileSummary[] {
  const [profiles, setProfiles] = useState<ConnectionProfileSummary[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch("/connections")
      .then((res) => res.json() as Promise<{ connections: ConnectionProfileSummary[] }>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.connections)) {
          setProfiles(data.connections);
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
