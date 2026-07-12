import { useState, type CSSProperties, type KeyboardEvent } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useGraphStore } from "../../store/graphStore";
import "./NoteNode.css";

export interface NoteNodeData extends Record<string, unknown> {
  content: string;
  color: string;
  anchorId: string | null;
}

type NoteNodeType = Node<NoteNodeData, "noteNode">;

const NOTE_COLORS: Record<string, { background: string; border: string }> = {
  yellow: { background: "#fef3c7", border: "#eab308" },
  pink: { background: "#fce7f3", border: "#ec4899" },
  blue: { background: "#dbeafe", border: "#3b82f6" },
  green: { background: "#dcfce7", border: "#22c55e" },
  purple: { background: "#f3e8ff", border: "#a855f7" },
};

const NOTE_TEXT_COLOR = "#1f2937";

const DEFAULT_COLOR = "yellow";

const boxStyleBase: CSSProperties = {
  width: 220,
  minHeight: 80,
  borderRadius: "var(--radius-md)",
  boxShadow: "var(--shadow-2)",
  padding: "var(--space-3)",
  boxSizing: "border-box",
  color: NOTE_TEXT_COLOR,
  fontSize: "var(--text-sm)",
};

export function NoteNode({ id, data }: NodeProps<NoteNodeType>): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(data.content);

  const swatch = NOTE_COLORS[data.color] ?? NOTE_COLORS[DEFAULT_COLOR];
  const boxStyle: CSSProperties = {
    ...boxStyleBase,
    background: swatch.background,
    border: `1px solid ${swatch.border}`,
  };

  function startEditing() {
    setDraft(data.content);
    setEditing(true);
  }

  function commit() {
    if (draft !== data.content) {
      setParam(id, "content", draft);
    }
    setEditing(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Escape") {
      setDraft(data.content);
      setEditing(false);
    }
  }

  return (
    <div style={boxStyle} data-testid="note-node">
      {editing ? (
        <textarea
          data-testid="note-node-editor"
          className="nodrag nowheel"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKeyDown}
          rows={Math.max(3, draft.split("\n").length)}
          style={{
            width: "100%",
            background: "transparent",
            border: "none",
            outline: "none",
            resize: "vertical",
            color: NOTE_TEXT_COLOR,
            fontSize: "var(--text-sm)",
            fontFamily: "inherit",
          }}
        />
      ) : (
        <div
          data-testid="note-node-preview"
          className="note-node-content"
          onDoubleClick={startEditing}
        >
          {data.content.trim() ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content}</ReactMarkdown>
          ) : (
            <span style={{ opacity: 0.6, fontStyle: "italic" }}>
              Double-click to add a note…
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default NoteNode;
