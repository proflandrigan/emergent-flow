// Validate analogue of CodePanel's compile effect: debounce-POSTs the current graph IR to the
// local server's `/validate` endpoint whenever the graph changes, and writes the resulting
// verdict into `validationStore`. The store's diagnostics/edgeCompatibility are what later
// drives edge colouring on the canvas -- this hook has no UI of its own.

import { useEffect } from "react";

import { useGraphStore } from "./graphStore";
import { useValidationStore } from "./validationStore";

export function useLiveValidation(debounceMs = 400): void {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);

  useEffect(() => {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      useValidationStore.getState().clear();
      return;
    }

    let cancelled = false;
    useValidationStore.getState().setValidating();
    const handle = setTimeout(() => {
      void (async () => {
        try {
          const res = await fetch("/validate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(graph),
          });
          const body = await res.json();
          if (cancelled) {
            return;
          }
          if (!res.ok || body.error) {
            useValidationStore.getState().setError(body.error ?? `Server error ${res.status}`);
          } else {
            useValidationStore.getState().setResult(body.diagnostics);
          }
        } catch (err) {
          if (!cancelled) {
            const msg = err instanceof Error ? err.message : String(err);
            useValidationStore.getState().setError("Could not reach server: " + msg);
          }
        }
      })();
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [nodes, edges, debounceMs]);
}
