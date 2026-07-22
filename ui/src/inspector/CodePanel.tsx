// Inspector's Code tab: debounce-compiles the current graph IR against the local server's
// `/compile` endpoint and renders the returned Python read-only with highlight.js syntax
// highlighting. One-way only (ADR 0001) -- this panel never parses code back into the graph.

import { useEffect, useRef, useState } from "react";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import "highlight.js/styles/atom-one-dark.css";

import { useGraphStore } from "../store/graphStore";

hljs.registerLanguage("python", python);

function findAssignmentLineIndex(code: string, varName: string | null | undefined): number {
  if (!varName) {
    return -1;
  }
  const pattern = new RegExp(`^\\s*${varName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*=`);
  const lines = code.split("\n");
  return lines.findIndex((line) => pattern.test(line));
}

// hljs.highlight() returns one HTML string for the whole source, and a single
// <span> can legitimately wrap text that spans multiple source lines (e.g. the
// module docstring emitted for every LLM-touching graph, compiler.py's
// `docstring_body`). Naively splitting that HTML on "\n" cuts those spans in
// half: the lines in the middle lose their highlight class entirely, and the
// boundary lines end up with an unmatched open/close tag. Track a stack of
// currently-open tags instead, closing them at each line boundary and
// reopening them at the start of the next line, so every returned line is
// self-contained HTML AND keeps the class an unbroken span would have applied.
function splitHighlightedByLine(html: string): string[] {
  const tagRe = /<span class="([^"]*)">|<\/span>/g;
  const openStack: string[] = [];
  const lines: string[] = [];
  let lineBuf = "";

  function flushLine(): void {
    lines.push(lineBuf + "</span>".repeat(openStack.length));
    lineBuf = "";
  }

  function appendText(text: string): void {
    const parts = text.split("\n");
    for (let i = 0; i < parts.length; i++) {
      lineBuf += parts[i];
      if (i < parts.length - 1) {
        flushLine();
        lineBuf = openStack.map((cls) => `<span class="${cls}">`).join("");
      }
    }
  }

  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = tagRe.exec(html)) !== null) {
    appendText(html.slice(lastIndex, match.index));
    if (match[0] === "</span>") {
      openStack.pop();
      lineBuf += "</span>";
    } else {
      openStack.push(match[1]);
      lineBuf += match[0];
    }
    lastIndex = tagRe.lastIndex;
  }
  appendText(html.slice(lastIndex));
  flushLine();
  return lines;
}

interface CodePanelProps {
  debounceMs?: number;
  highlightVarName?: string | null;
}

export function CodePanel({
  debounceMs = 400,
  highlightVarName = null,
}: CodePanelProps): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const highlightedLineRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    highlightedLineRef.current?.scrollIntoView({ block: "center" });
  }, [highlightVarName, code]);

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
          <code className="hljs language-python">
            {(() => {
              const highlighted = hljs.highlight(code ?? "", { language: "python" }).value;
              const highlightIndex = findAssignmentLineIndex(code ?? "", highlightVarName);
              return splitHighlightedByLine(highlighted).map((lineHtml, i) => (
                <div
                  key={i}
                  ref={i === highlightIndex ? highlightedLineRef : undefined}
                  data-testid={i === highlightIndex ? "code-highlighted-line" : undefined}
                  style={
                    i === highlightIndex
                      ? { background: "var(--accent-soft)" }
                      : undefined
                  }
                  dangerouslySetInnerHTML={{ __html: lineHtml || " " }}
                />
              ));
            })()}
          </code>
        </pre>
      )}
    </div>
  );
}
