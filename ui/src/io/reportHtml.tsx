// Client-side standalone HTML report of the graph's `reports.result_card` nodes. Pure: takes the
// nodes + execution results, returns a complete HTML document string. All user text is escaped.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { renderToStaticMarkup } from "react-dom/server";

import {
  parseBlocks,
  splitSource,
  type ResultCardBlock,
} from "../canvas/resultCardBlocks";
import { PayloadView } from "../inspector/PayloadView";
import type { Payload } from "../store/execution";
import type { NodeModel } from "../store/model";

export interface ReportCard {
  title: string;
  blocks: ResultCardBlock[];
}

const RESULT_CARD_TYPE = "reports.result_card";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// PayloadView / ReportView render `html` payloads in `<iframe sandbox="allow-scripts">`, which is
// right for the live inspector but would run payload script when the exported file is opened.
// Strip it to a fully-sandboxed iframe (no scripts) in the static export.
function lockDownIframes(markup: string): string {
  return markup.replace(/ sandbox="[^"]*"/g, ' sandbox=""');
}

function paramValue(node: NodeModel, name: string): unknown {
  return node.params.find((p) => p.name === name)?.value;
}

export function collectReportCards(nodes: Record<string, NodeModel>): ReportCard[] {
  return Object.values(nodes)
    .filter((n) => n.type === RESULT_CARD_TYPE)
    .sort((a, b) => a.position.y - b.position.y || a.position.x - b.position.x)
    .map((n) => {
      const title = paramValue(n, "title");
      return {
        title: typeof title === "string" && title !== "" ? title : "Results",
        blocks: parseBlocks(paramValue(n, "blocks_json")),
      };
    });
}

const STYLE = `
:root { --text-secondary: #5b6270; --border-subtle: #d5d9e0; --surface-1: #ffffff; --surface-2: #f3f4f7; }
@media (prefers-color-scheme: dark) {
  :root { --text-secondary: #a0a7b4; --border-subtle: #3a3f4b; --surface-1: #15171c; --surface-2: #1e2128; }
}
body { font-family: system-ui, sans-serif; background: var(--surface-1); color: CanvasText; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
section { margin-bottom: 2.5rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid var(--border-subtle); padding: 0.2rem 0.5rem; }
img { max-width: 100%; }
pre { background: var(--surface-2); padding: 0.5rem; overflow-x: auto; }
.muted, .caption { color: var(--text-secondary); }
.caption { font-size: 0.85rem; }
`;

function renderBlock(
  block: ResultCardBlock,
  results: Record<string, Record<string, Payload>>,
): string {
  if (block.kind === "markdown") {
    return lockDownIframes(
      renderToStaticMarkup(<ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>),
    );
  }
  const split = splitSource(block.source);
  const payload = split ? results[split.nodeId]?.[split.port] : undefined;
  let out = payload
    ? `<div>${lockDownIframes(renderToStaticMarkup(<PayloadView payload={payload} />))}</div>`
    : `<p class="muted">No result available (graph not run).</p>`;
  if (block.caption !== "") {
    out += `<p class="caption">${escapeHtml(block.caption)}</p>`;
  }
  return out;
}

export function buildReportHtml(opts: {
  graphName: string;
  cards: ReportCard[];
  results: Record<string, Record<string, Payload>>;
}): string {
  const body =
    opts.cards.length === 0
      ? "<p>No result cards in this graph.</p>"
      : opts.cards
          .map(
            (card) =>
              `<section><h2>${escapeHtml(card.title)}</h2>${card.blocks
                .map((b) => renderBlock(b, opts.results))
                .join("\n")}</section>`,
          )
          .join("\n");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="script-src 'none'; object-src 'none'">
<title>${escapeHtml(opts.graphName)}</title>
<style>${STYLE}</style>
</head>
<body>
${body}
</body>
</html>
`;
}
