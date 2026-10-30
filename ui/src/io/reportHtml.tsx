// Client-side standalone HTML report of the graph's `reports.result_card` nodes. Pure: takes the
// nodes + execution results, returns a complete HTML document string. All user text is escaped.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { renderToStaticMarkup } from "react-dom/server";

import {
  formatRunEvidence,
  parseBlocks,
  resolveBlockState,
  type ResultCardBlock,
} from "../canvas/resultCardBlocks";
import { PayloadView } from "../inspector/PayloadView";
import type { Tour, TourStep } from "../session/sessionClient";
import type { NodeRunStatus, Payload, RunMeta } from "../store/execution";
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
.conclusion { border-left: 3px solid var(--border-subtle); padding-left: 0.75rem; }
.open-questions { border-left: 3px solid #d97706; padding-left: 0.75rem; }
.anchors, .evidence { font-size: 0.85rem; }
`;

function renderMarkdown(text: string): string {
  return lockDownIframes(
    renderToStaticMarkup(<ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>),
  );
}

// Plain-text (unescaped) description of where a tour step points; callers must escape it.
export function describeTourStepAnchors(step: TourStep): string {
  if (step.route) {
    return `Route: ${step.route[0]} \u2192 ${step.route[1]}`;
  }
  if (step.focus && step.focus.length > 0) {
    const reach = step.reach ? ` (reach ${step.reach})` : "";
    return `Focus: ${step.focus.join(", ")}${reach}`;
  }
  return "";
}

function renderTour(tour: Tour): string {
  const steps = tour.steps
    .map((step) => {
      const anchors = describeTourStepAnchors(step);
      const unknowns = step.unknowns ?? [];
      return (
        "<li>" +
        (anchors !== "" ? `<p class="muted anchors">${escapeHtml(anchors)}</p>` : "") +
        renderMarkdown(step.note) +
        (unknowns.length > 0
          ? `<div class="open-questions"><strong>Open questions</strong><ul>${unknowns
              .map((u) => `<li>${escapeHtml(u)}</li>`)
              .join("")}</ul></div>`
          : "") +
        "</li>"
      );
    })
    .join("\n");
  return (
    `<article class="tour"><h3>${escapeHtml(tour.title)}</h3>` +
    `<p class="muted">by ${escapeHtml(tour.author)}</p>` +
    `<div class="conclusion"><strong>Conclusion</strong>${renderMarkdown(tour.conclusion)}</div>` +
    `<ol class="tour-steps">${steps}</ol></article>`
  );
}

interface RenderContext {
  results: Record<string, Record<string, Payload>>;
  statuses: Record<string, NodeRunStatus>;
  nodeRunMeta: Record<string, RunMeta>;
  nodeLabels: Record<string, string>;
}

function renderBlock(block: ResultCardBlock, ctx: RenderContext): string {
  if (block.kind === "markdown") {
    return renderMarkdown(block.text);
  }
  const resolved = resolveBlockState(block, ctx.results, ctx.statuses, ctx.nodeRunMeta);
  const evidence = formatRunEvidence(resolved.runId, resolved.finishedAt, true);
  const label = ctx.nodeLabels[resolved.nodeId];
  const sourceText = `Source: ${label ? `${label} (${resolved.nodeId})` : resolved.nodeId}, port ${resolved.port}`;
  let out: string;
  if (resolved.state === "ok" && resolved.payload) {
    out = `<div>${lockDownIframes(renderToStaticMarkup(<PayloadView payload={resolved.payload} />))}</div>`;
    out += `<p class="muted evidence">${escapeHtml(sourceText)}${evidence !== "" ? ` \u00b7 ${escapeHtml(evidence)}` : ""}</p>`;
  } else if (resolved.state === "failed") {
    out = `<p class="muted">Source failed \u2014 no result available.</p>`;
    out += `<p class="muted evidence">${escapeHtml(sourceText)}</p>`;
  } else {
    out = `<p class="muted">No result available (graph not run).</p>`;
    out += `<p class="muted evidence">${escapeHtml(sourceText)}</p>`;
  }
  if (block.caption !== "") {
    out += `<p class="caption">${escapeHtml(block.caption)}</p>`;
  }
  return out;
}

export function buildReportHtml(opts: {
  graphName: string;
  cards: ReportCard[];
  results: Record<string, Record<string, Payload>>;
  /** Per-node run statuses; lets the report tell a failed source from one never run. */
  statuses?: Record<string, NodeRunStatus>;
  /** Per-node identity (run id + UTC finish time) of the run each node's result came from. */
  nodeRunMeta?: Record<string, RunMeta>;
  /** node id -> display label, used for the evidence line. */
  nodeLabels?: Record<string, string>;
  tours?: Tour[];
}): string {
  const tours = opts.tours ?? [];
  const ctx: RenderContext = {
    results: opts.results,
    statuses: opts.statuses ?? {},
    nodeRunMeta: opts.nodeRunMeta ?? {},
    nodeLabels: opts.nodeLabels ?? {},
  };
  const cardsBody =
    opts.cards.length === 0
      ? tours.length === 0
        ? "<p>No result cards in this graph.</p>"
        : ""
      : opts.cards
          .map(
            (card) =>
              `<section><h2>${escapeHtml(card.title)}</h2>${card.blocks
                .map((b) => renderBlock(b, ctx))
                .join("\n")}</section>`,
          )
          .join("\n");
  const toursBody =
    tours.length === 0
      ? ""
      : `<section class="tours"><h2>Guided tours</h2>${tours.map(renderTour).join("\n")}</section>`;
  const body = cardsBody !== "" && toursBody !== "" ? `${cardsBody}\n${toursBody}` : cardsBody + toursBody;
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
