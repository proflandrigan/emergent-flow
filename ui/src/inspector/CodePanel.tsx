// Inspector's Code tab: debounce-compiles the current graph IR against the local server's
// `/compile` endpoint and renders the returned Python read-only with highlight.js syntax
// highlighting. One-way only (ADR 0001) -- this panel never parses code back into the graph.

import { useEffect, useState } from "react";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import "highlight.js/styles/atom-one-dark.css";

import { useGraphStore } from "../store/graphStore";

hljs.registerLanguage("python", python);

interface CodePanelProps {
  debounceMs?: number;
}

export function CodePanel({ debounceMs = 400 }: CodePanelProps): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setCode(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(() => {
      void (async () => {
        try {
          const res = await fetch("/compile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(graph),
          });
          const body = await res.json();
          if (cancelled) {
            return;
          }
          if (!res.ok || body.error) {
            setError(body.error ?? `Server error ${res.status}`);
            setCode(null);
          } else {
            setCode(body.code);
            setError(null);
          }
        } catch (err) {
          if (!cancelled) {
            const msg = err instanceof Error ? err.message : String(err);
            setError("Could not reach server: " + msg);
            setCode(null);
          }
        } finally {
          if (!cancelled) {
            setLoading(false);
          }
        }
      })();
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [nodes, edges, debounceMs]);

  // Distinguish "no graph yet" from "compiling the first result": an empty graph shows the
  // empty state; a non-empty graph with no code yet falls through to the loading indicator
  // below (rather than misleadingly telling the user to add nodes).
  if (Object.keys(nodes).length === 0) {
    return (
      <p data-testid="code-empty" style={{ color: "var(--text-secondary)" }}>
        Add nodes to see generated code.
      </p>
    );
  }

  return (
    <div>
      {loading && !error ? (
        <p data-testid="code-loading" style={{ color: "var(--text-secondary)" }}>
          Compiling...
        </p>
      ) : null}
      {error ? (
        <pre
          data-testid="code-error"
          style={{
            color: "var(--danger)",
            whiteSpace: "pre-wrap",
            background: "var(--surface-1)",
            fontFamily: "var(--font-mono)",
            padding: "var(--space-2)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {error}
        </pre>
      ) : (
        <pre
          data-testid="code-output"
          style={{
            margin: 0,
            overflow: "auto",
            background: "var(--surface-1)",
            fontFamily: "var(--font-mono)",
            padding: "var(--space-2)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          <code
            className="hljs language-python"
            dangerouslySetInnerHTML={{
              __html: hljs.highlight(code ?? "", { language: "python" }).value,
            }}
          />
        </pre>
      )}
    </div>
  );
}
