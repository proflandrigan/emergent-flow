// Fetch the live node catalog from the server, falling back to the committed static
// catalog (ADR 0014 Decision 5 -- both delivery channels) so the palette works offline / in
// tests with no server running.

import { useEffect, useState } from "react";

import staticCatalog from "../generated/catalog.json";
import type { Catalog } from "./types";

const FALLBACK = staticCatalog as unknown as Catalog;

// Start from the committed catalog (works offline / in tests), then upgrade to the live
// server catalog when reachable. The canvas is a pure consumer of /catalog (ADR 0013).
export function useCatalog(): Catalog {
  const [catalog, setCatalog] = useState<Catalog>(FALLBACK);
  useEffect(() => {
    let cancelled = false;
    fetch("/catalog")
      .then((res) => res.json() as Promise<Catalog>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.nodes)) {
          setCatalog(data);
        }
      })
      .catch(() => {
        /* keep the static fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return catalog;
}
