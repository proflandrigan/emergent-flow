import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Check, ClipboardList, Pencil } from "lucide-react";
import { useMemo, useState, type CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import "./ResultCardNode.css";
import { PayloadView } from "../../inspector/PayloadView";
import { useExecutionStore } from "../../store/executionStore";
import { useGraphStore } from "../../store/graphStore";
import {
  formatRunEvidence,
  resolveBlockState,
  serializeBlocks,
  type ResultCardBlock,
} from "../resultCardBlocks";

export interface ResultCardNodeData extends Record<string, unknown> {
  title: string;
  blocks: ResultCardBlock[];
  width: number;
  inPortId: string | null;
}

export type ResultCardNodeType = Node<ResultCardNodeData, "resultCardNode">;

const containerStyle: CSSProperties = {
  borderRadius: "var(--radius-md)",
  background: "var(--surface-1)",
  fontSize: 12,
  boxSizing: "border-box",
  position: "relative",
  boxShadow: "var(--shadow-2)",
  border: "1px solid var(--border-subtle)",
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-1)",
  padding: "var(--space-1) var(--space-2)",
  borderTopLeftRadius: "var(--radius-md)",
  borderTopRightRadius: "var(--radius-md)",
  background: "var(--surface-2)",
  borderBottom: "1px solid var(--border-subtle)",
  fontSize: 12,
  fontWeight: 600,
  color: "var(--text-secondary)",
};

const bodyStyle: CSSProperties = {
  padding: "var(--space-1) var(--space-2)",
  maxHeight: 480,
  overflow: "auto",
};

const mutedStyle: CSSProperties = {
  color: "var(--text-secondary)",
  fontStyle: "italic",
};

function ResultBlockView({
  block,
}: {
  block: Extract<ResultCardBlock, { kind: "result" }>;
}): JSX.Element {
  const results = useExecutionStore((s) => s.results);
  const statuses = useExecutionStore((s) => s.statuses);
  const runMeta = useExecutionStore((s) => s.runMeta);

  const resolved = resolveBlockState(block, results, statuses, runMeta);
  const evidence = formatRunEvidence(resolved.runId, resolved.finishedAt);

  let content: JSX.Element;
  if (resolved.state === "ok" && resolved.payload) {
    content = <PayloadView payload={resolved.payload} />;
  } else if (resolved.state === "failed") {
    content = (
      <span data-testid="result-card-error" style={mutedStyle}>
        Source failed
      </span>
    );
  } else {
    content = (
      <span data-testid="result-card-pending" style={mutedStyle}>
        Not run yet — run the graph to see this result.
      </span>
    );
  }

  return (
    <div data-testid="result-card-block-result" style={{ margin: "var(--space-1) 0" }}>
      {content}
      {resolved.state === "ok" && evidence !== "" ? (
        <div
          data-testid="result-card-evidence"
          title={resolved.runId ? `Run ID: ${resolved.runId}` : undefined}
          style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}
        >
          {evidence}
        </div>
      ) : null}
      {block.caption ? (
        <div
          data-testid="result-card-caption"
          style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}
        >
          {block.caption}
        </div>
      ) : null}
    </div>
  );
}

interface UpstreamOption {
  source: string;
  label: string;
}

const controlsStyle: CSSProperties = {
  display: "flex",
  gap: "var(--space-1)",
  justifyContent: "flex-end",
  margin: "2px 0",
};

const editorStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  minHeight: 60,
  fontSize: 12,
  fontFamily: "inherit",
};

const footerStyle: CSSProperties = {
  display: "flex",
  gap: "var(--space-1)",
  padding: "var(--space-1) var(--space-2)",
  borderTop: "1px solid var(--border-subtle)",
};

const iconButtonStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  marginLeft: "auto",
  background: "transparent",
  border: "none",
  cursor: "pointer",
  color: "inherit",
  padding: 0,
};

export function ResultCardNode({ id, data }: NodeProps<ResultCardNodeType>): JSX.Element {
  const [editing, setEditing] = useState(false);
  const setParam = useGraphStore((s) => s.setParam);
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);

  const upstream = useMemo<UpstreamOption[]>(() => {
    const out: UpstreamOption[] = [];
    const seen = new Set<string>();
    for (const edge of Object.values(edges)) {
      if (edge.target.node_id !== id) {
        continue;
      }
      const n = nodes[edge.source.node_id];
      const p = n?.ports.find((port) => port.id === edge.source.port_id);
      if (!n || !p) {
        continue;
      }
      const source = `${n.id}:${p.name}`;
      if (seen.has(source)) {
        continue;
      }
      seen.add(source);
      out.push({ source, label: `${n.label ?? n.type} → ${p.label ?? p.name}` });
    }
    return out;
  }, [edges, nodes, id]);

  const commit = (next: ResultCardBlock[]): void => {
    setParam(id, "blocks_json", serializeBlocks(next));
  };

  const move = (index: number, delta: number): void => {
    const target = index + delta;
    if (target < 0 || target >= data.blocks.length) {
      return;
    }
    const next = [...data.blocks];
    const [item] = next.splice(index, 1);
    if (item === undefined) {
      return;
    }
    next.splice(target, 0, item);
    commit(next);
  };

  const replaceAt = (index: number, block: ResultCardBlock): void => {
    commit(data.blocks.map((b, i) => (i === index ? block : b)));
  };

  return (
    <div data-testid="result-card-node" style={{ ...containerStyle, width: data.width }}>
      {data.inPortId ? (
        <Handle
          type="target"
          position={Position.Left}
          id={data.inPortId}
          style={{ top: 16 }}
        />
      ) : null}
      <div style={headerStyle}>
        <ClipboardList size={12} />
        {editing ? (
          <input
            data-testid="result-card-title-input"
            className="nodrag"
            defaultValue={data.title}
            onBlur={(e) => setParam(id, "title", e.target.value)}
          />
        ) : (
          <span data-testid="result-card-title">{data.title}</span>
        )}
        <button
          type="button"
          className="nodrag"
          data-testid="result-card-edit-toggle"
          aria-label={editing ? "Done editing" : "Edit card"}
          style={iconButtonStyle}
          onClick={() => setEditing((v) => !v)}
        >
          {editing ? <Check size={12} /> : <Pencil size={12} />}
        </button>
      </div>
      <div className="result-card-body nodrag nowheel" style={bodyStyle}>
        {data.blocks.length === 0 ? (
          <span data-testid="result-card-empty" style={mutedStyle}>
            Empty card — add prose or results.
          </span>
        ) : (
          data.blocks.map((block, index) => (
            <div key={index}>
              {editing ? (
                <div data-testid="result-card-block-controls" style={controlsStyle}>
                  <button
                    type="button"
                    className="nodrag"
                    aria-label="Move up"
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="nodrag"
                    aria-label="Move down"
                    disabled={index === data.blocks.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="nodrag"
                    aria-label="Remove"
                    onClick={() => commit(data.blocks.filter((_, i) => i !== index))}
                  >
                    ×
                  </button>
                </div>
              ) : null}
              {block.kind === "markdown" ? (
                editing ? (
                  <textarea
                    key={`${index}:${block.text}`}
                    data-testid="result-card-md-editor"
                    className="nodrag nowheel"
                    style={editorStyle}
                    defaultValue={block.text}
                    onBlur={(e) => {
                      if (e.target.value !== block.text) {
                        replaceAt(index, { kind: "markdown", text: e.target.value });
                      }
                    }}
                  />
                ) : (
                  <div
                    className="result-card-md"
                    data-testid="result-card-block-markdown"
                    onDoubleClick={() => setEditing(true)}
                  >
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
                  </div>
                )
              ) : (
                <>
                  <ResultBlockView block={block} />
                  {editing ? (
                    <input
                      key={`${index}:${block.caption}`}
                      data-testid="result-card-caption-input"
                      className="nodrag"
                      defaultValue={block.caption}
                      placeholder="Caption"
                      onBlur={(e) => {
                        if (e.target.value !== block.caption) {
                          replaceAt(index, { ...block, caption: e.target.value });
                        }
                      }}
                    />
                  ) : null}
                </>
              )}
            </div>
          ))
        )}
      </div>
      {editing ? (
        <div style={footerStyle}>
          <button
            type="button"
            className="nodrag"
            data-testid="result-card-add-text"
            onClick={() => commit([...data.blocks, { kind: "markdown", text: "" }])}
          >
            Add text
          </button>
          <select
            className="nodrag"
            data-testid="result-card-add-result"
            value=""
            disabled={upstream.length === 0}
            onChange={(e) => {
              if (e.target.value !== "") {
                commit([...data.blocks, { kind: "result", source: e.target.value, caption: "" }]);
              }
            }}
          >
            <option value="">
              {upstream.length === 0 ? "Wire inputs to add results" : "Add result…"}
            </option>
            {upstream.map((u) => (
              <option key={u.source} value={u.source}>
                {u.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}
    </div>
  );
}

export default ResultCardNode;
