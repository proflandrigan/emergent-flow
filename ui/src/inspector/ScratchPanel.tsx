// Inspector's Scratch tab (issue #178 task 2): an ad-hoc `def transform(value):` run against one
// node output's *stored* artifact, for one-off EDA questions. Draft state lives in `scratchStore`
// (in memory, never in the graph). "Save as code node" is the only action that touches the
// graph, and it does so in a single undo step; "Discard" clears scratch state only.

import { useCatalog } from "../catalog/useCatalog";
import { HISTORY_LIMIT, useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { isPromotable, useScratchStore } from "../store/scratchStore";
import { CodeEditor } from "./CodeEditor";
import { PayloadView } from "./PayloadView";

const CUSTOM_CODE_TYPE = "script.custom_code";

const mutedStyle = { color: "var(--text-secondary)" } as const;
const preStyle = { whiteSpace: "pre-wrap", margin: 0, fontSize: 11 } as const;

export interface ScratchPanelProps {
  /** Called after "Save as code node" or "Discard" so the host can leave the scratch tab. */
  onDone?: () => void;
}

export function ScratchPanel({ onDone }: ScratchPanelProps): JSX.Element {
  const catalog = useCatalog();
  const activeKey = useScratchStore((s) => s.activeKey);
  const draft = useScratchStore((s) => (s.activeKey ? s.drafts[s.activeKey] : undefined));

  if (!activeKey || !draft) {
    return (
      <p data-testid="scratch-empty" style={mutedStyle}>
        Use “Explore this output” on a result to start a scratch.
      </p>
    );
  }

  const { outcome } = draft;
  const current = outcome !== null && outcome.code === draft.code;
  const stale = outcome?.status === "expired" || outcome?.status === "revision_mismatch";
  // Promotable only once THIS exact code has run and the server says it can become a code node
  // (`promotable` on the /scratch/run response; see isPromotable for the older-server fallback).
  const promotable = current && isPromotable(outcome);
  const spec = catalog.nodes.find((n) => n.type === CUSTOM_CODE_TYPE);
  const canSave = promotable && spec !== undefined;
  const saveBlockedReason = canSave
    ? undefined
    : current && !stale && outcome.promotableReason
      ? outcome.promotableReason
      : "Run code that parses and defines transform() first";

  const run = (): void => {
    void useScratchStore.getState().run(activeKey);
  };

  const saveAsNode = (): void => {
    if (!canSave || !spec) return;
    const graph = useGraphStore.getState();
    const source = graph.nodes[draft.nodeId];
    const outPort = source?.ports.find((p) => p.direction === "out" && p.name === draft.port);
    if (!source || !outPort) return;
    // addNodeFromSpec / setParam / connect each push history; keep only the first snapshot
    // (the pre-promotion state) so the promotion is ONE undo step.
    const pastBefore = graph.past;
    const nodeId = graph.addNodeFromSpec(spec, {
      x: source.position.x + 240,
      y: source.position.y,
    });
    const pastNow = useGraphStore.getState().past;
    const first = pastNow[pastNow.length - 1];
    graph.setParam(nodeId, "code", draft.code);
    const inPort = useGraphStore
      .getState()
      .nodes[nodeId]?.ports.find((p) => p.direction === "in");
    if (inPort) {
      graph.connect(
        { node_id: source.id, port_id: outPort.id },
        { node_id: nodeId, port_id: inPort.id },
      );
    }
    const past = first ? [...pastBefore, first] : [...pastBefore];
    if (past.length > HISTORY_LIMIT) {
      past.shift();
    }
    useGraphStore.setState({ past, _lastTxn: "promoteScratch" });
    useSelectionStore.getState().replaceSelection([nodeId]);
    useScratchStore.getState().discard(activeKey);
    onDone?.();
  };

  const discard = (): void => {
    useScratchStore.getState().discard(activeKey);
    onDone?.();
  };

  return (
    <div
      data-testid="scratch-panel"
      onKeyDown={(e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
          e.preventDefault();
          run();
        }
      }}
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}
    >
      <div data-testid="scratch-bound" style={{ ...mutedStyle, fontSize: 11 }}>
        Bound to: {draft.nodeLabel} / {draft.port} / {draft.revision.slice(0, 8)}
      </div>
      <CodeEditor
        value={draft.code}
        language="python"
        testId="scratch-editor"
        onChange={(code) => useScratchStore.getState().setCode(activeKey, code)}
        errorLine={outcome?.status === "error" && current ? outcome.error?.line : null}
      />
      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <button type="button" data-testid="scratch-run" disabled={draft.running} onClick={run}>
          {draft.running ? "Running…" : "Run"} <span style={mutedStyle}>(⌘/Ctrl+Enter)</span>
        </button>
        <button
          type="button"
          data-testid="scratch-save"
          disabled={!canSave}
          title={saveBlockedReason}
          onClick={saveAsNode}
        >
          Save as code node
        </button>
        <button type="button" data-testid="scratch-discard" onClick={discard}>
          Discard
        </button>
      </div>
      {!canSave && current && !stale && outcome.promotableReason ? (
        <div data-testid="scratch-save-reason" style={{ ...mutedStyle, fontSize: 11 }}>
          Can’t save as a code node: {outcome.promotableReason}
        </div>
      ) : null}
      {stale ? (
        <div data-testid="scratch-stale" style={{ color: "var(--danger)" }}>
          {outcome.status === "expired"
            ? "This output is no longer stored. Re-run the node, then use “Explore this output” " +
              "again to rebind this scratch (your code is kept)."
            : "This node was re-run, so the output you explored was replaced. Use “Explore this " +
              "output” on the new result to rebind this scratch to it (your code is kept)."}
        </div>
      ) : null}
      {outcome?.status === "error" && outcome.error ? (
        <div data-testid="scratch-error" style={{ color: "var(--danger)" }}>
          <strong>
            {outcome.error.type}
            {outcome.error.line ? ` (line ${outcome.error.line})` : ""}
          </strong>
          : {outcome.error.message}
          {outcome.error.traceback ? (
            <pre style={preStyle}>{outcome.error.traceback}</pre>
          ) : null}
        </div>
      ) : null}
      {outcome?.stdout ? (
        <pre data-testid="scratch-stdout" style={preStyle}>
          {outcome.stdout}
        </pre>
      ) : null}
      {outcome?.stderr ? (
        <pre data-testid="scratch-stderr" style={{ ...preStyle, color: "var(--danger)" }}>
          {outcome.stderr}
        </pre>
      ) : null}
      {outcome?.status === "ok" && outcome.result ? (
        <div data-testid="scratch-result">
          <PayloadView payload={outcome.result} />
        </div>
      ) : null}
    </div>
  );
}
