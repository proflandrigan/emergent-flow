// Chat modal (agent chat feature): the human's entry point into an in-app, multi-turn chat with
// a spawned coding-agent CLI (Claude Code, opencode, Gemini CLI, Codex) collaborating on this
// graph. Replaces the old "Share session"/session-id-handoff flow -- this
// component both starts the underlying graph session (if none is active yet) and drives the
// chat itself. Two visual modes: expanded (a docked glass panel that overlays the Inspector's
// slot, top-right) and collapsed (a small floating status pill so the canvas stays usable while
// a spawned agent works in the background) -- both modes read the SAME useSessionStore state, so
// collapsing/expanding never loses anything; server-side chat state (and the spawned subprocess)
// is unaffected by which mode is rendered or whether this component is mounted at all.
//
// BackendPicker (idle state) starts the chat; ActiveChat renders the live message list (each
// turn's human message, tool-call narration lines, and agent reply) plus an input row that
// sends a new message or, while the latest turn is RUNNING, shows a Stop button instead. "End
// chat" is disabled while the latest turn is RUNNING -- SessionStore.end_chat (server) doesn't
// itself interrupt a running turn, so the UI must route through Stop first.

import { useEffect, useRef, useState, type JSX } from "react";
import { X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { Select } from "../ui/Select";
import { COMMAND_BAR_CLEARANCE } from "../App";
import { GatePanel } from "./GatePanel";
import { ProposalPanel } from "./ProposalPanel";
import { ReviewPanel } from "./ReviewPanel";
import { getAvailableAgents, type ChatTurn } from "./sessionClient";
import { useSessionStore } from "./sessionStore";

export interface ChatModalProps {
  onClose: () => void;
}

function ChatPill({
  label,
  onExpand,
}: {
  label: string;
  onExpand: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      className="glass"
      data-testid="chat-modal-pill"
      onClick={onExpand}
      style={{
        position: "fixed",
        top: "var(--space-4)",
        right: "var(--space-4)",
        zIndex: 20,
        display: "flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-2) var(--space-3)",
        borderRadius: "var(--radius-full, 999px)",
        color: "var(--text-primary)",
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

function BackendPicker(): JSX.Element {
  const startChat = useSessionStore((s) => s.startChat);
  const [agents, setAgents] = useState<string[] | null>(null);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [selectedBackend, setSelectedBackend] = useState("");
  const [draftMessage, setDraftMessage] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAvailableAgents()
      .then((names) => {
        if (cancelled) return;
        setAgents(names);
        if (names.length > 0) setSelectedBackend(names[0]);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setAgentsError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleStart = (): void => {
    if (!selectedBackend || draftMessage.trim() === "") return;
    setStarting(true);
    setStartError(null);
    startChat(selectedBackend, draftMessage.trim())
      .then(() => {
        setDraftMessage("");
      })
      .catch((err: unknown) => {
        setStartError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setStarting(false);
      });
  };

  return (
    <div data-testid="chat-backend-picker">
      <div style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>
        Start chat
      </div>
      {agentsError ? (
        <div data-testid="chat-agents-error" style={{ color: "var(--danger)" }}>
          {agentsError}
        </div>
      ) : agents === null ? (
        <p style={{ color: "var(--text-secondary)" }}>
          Looking for coding-agent CLIs&hellip;
        </p>
      ) : agents.length === 0 ? (
        <p
          data-testid="chat-no-agents"
          style={{ color: "var(--text-secondary)" }}
        >
          No coding-agent CLIs detected on this machine.
        </p>
      ) : (
        <>
          <Select
            data-testid="chat-backend-select"
            value={selectedBackend}
            onChange={(e) => setSelectedBackend(e.target.value)}
            style={{ marginBottom: "var(--space-2)", width: "100%" }}
          >
            {agents.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
          <textarea
            data-testid="chat-draft-message"
            value={draftMessage}
            onChange={(e) => setDraftMessage(e.target.value)}
            placeholder="What do you want the agent to do?"
            rows={3}
            style={{ width: "100%", marginBottom: "var(--space-2)" }}
          />
          <Button
            variant="primary"
            data-testid="chat-start-button"
            disabled={starting || draftMessage.trim() === "" || selectedBackend === ""}
            onClick={handleStart}
          >
            {starting ? "Starting\u2026" : "Start chat"}
          </Button>
          {startError ? (
            <div
              data-testid="chat-start-error"
              style={{ color: "var(--danger)", marginTop: "var(--space-2)" }}
            >
              {startError}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function ChatTurnActivity({ turn }: { turn: ChatTurn }): JSX.Element | null {
  const [open, setOpen] = useState(turn.status === "failed");
  useEffect(() => {
    if (turn.status === "failed") setOpen(true);
  }, [turn.status]);

  if (turn.narration.length === 0) return null;
  const n = turn.narration.length;
  return (
    <details
      data-testid="chat-turn-activity"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      style={{
        margin: "0 0 var(--space-1)",
        color: "var(--text-secondary)",
        fontSize: "var(--text-sm)",
      }}
    >
      <summary
        data-testid="chat-turn-activity-summary"
        style={{ cursor: "pointer" }}
      >
        Worked through {n} step{n === 1 ? "" : "s"}
      </summary>
      <div style={{ marginTop: "var(--space-1)" }}>
        {turn.narration.map((line, i) => (
          <div key={i}>&rarr; {line}</div>
        ))}
      </div>
    </details>
  );
}

function ChatTurnView({ turn }: { turn: ChatTurn }): JSX.Element {
  return (
    <div data-testid="chat-turn" style={{ marginBottom: "var(--space-3)" }}>
      <div style={{ marginBottom: "var(--space-1)" }}>
        <strong>You:</strong> {turn.user_message}
      </div>
      <ChatTurnActivity turn={turn} />
      {turn.status === "completed" && turn.agent_message !== null ? (
        <div data-testid="chat-turn-agent-message">
          <strong>Agent:</strong>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {turn.agent_message}
          </ReactMarkdown>
        </div>
      ) : null}
      {turn.status === "failed" ? (
        <div style={{ color: "var(--danger)" }}>
          <strong>Agent:</strong> failed — {turn.error ?? "unknown error"}
        </div>
      ) : null}
      {turn.status === "interrupted" ? (
        <div style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>
          turn interrupted by user
        </div>
      ) : null}
      {turn.status === "running" ? (
        <div style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>
          working&hellip;
        </div>
      ) : null}
    </div>
  );
}

function ActiveChat({ backend }: { backend: string }): JSX.Element {
  const chat = useSessionStore((s) => s.chat);
  const startChat = useSessionStore((s) => s.startChat);
  const stopChat = useSessionStore((s) => s.stopChat);
  const endChat = useSessionStore((s) => s.endChat);
  const [ending, setEnding] = useState(false);
  const [draftMessage, setDraftMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);

  const latestTurn = chat.turns[chat.turns.length - 1];
  const turnRunning = latestTurn?.status === "running";

  const handleEnd = (): void => {
    setEnding(true);
    void endChat().finally(() => setEnding(false));
  };

  const handleSend = (): void => {
    if (draftMessage.trim() === "") return;
    setSending(true);
    setSendError(null);
    startChat(backend, draftMessage.trim())
      .then(() => {
        setDraftMessage("");
      })
      .catch((err: unknown) => {
        setSendError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setSending(false);
      });
  };

  const handleStop = (): void => {
    if (latestTurn === undefined) return;
    setStopping(true);
    void stopChat(latestTurn.id).finally(() => setStopping(false));
  };

  return (
    <div data-testid="chat-active-view">
      <div style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>
        Chatting with {backend}
      </div>
      <div
        data-testid="chat-message-list"
        style={{
          maxHeight: 320,
          overflowY: "auto",
          marginBottom: "var(--space-2)",
        }}
      >
        {chat.turns.length === 0 ? (
          <p style={{ color: "var(--text-secondary)" }}>No messages yet.</p>
        ) : (
          chat.turns.map((turn) => <ChatTurnView key={turn.id} turn={turn} />)
        )}
      </div>
      <div
        style={{
          display: "flex",
          gap: "var(--space-2)",
          marginBottom: "var(--space-2)",
        }}
      >
        <textarea
          data-testid="chat-message-input"
          value={draftMessage}
          onChange={(e) => setDraftMessage(e.target.value)}
          placeholder="Send a message"
          rows={2}
          disabled={turnRunning || sending}
          style={{ flex: 1 }}
        />
        {turnRunning ? (
          <Button
            variant="secondary"
            data-testid="chat-stop-button"
            disabled={stopping}
            onClick={handleStop}
          >
            {stopping ? "Stopping\u2026" : "Stop"}
          </Button>
        ) : (
          <Button
            variant="primary"
            data-testid="chat-send-button"
            disabled={sending || draftMessage.trim() === ""}
            onClick={handleSend}
          >
            {sending ? "Sending\u2026" : "Send"}
          </Button>
        )}
      </div>
      {sendError ? (
        <div
          data-testid="chat-send-error"
          style={{ color: "var(--danger)", marginBottom: "var(--space-2)" }}
        >
          {sendError}
        </div>
      ) : null}
      <Button
        variant="secondary"
        data-testid="chat-end-button"
        disabled={ending || turnRunning}
        title={
          turnRunning ? "Stop the running turn before ending the chat" : undefined
        }
        onClick={handleEnd}
      >
        {ending ? "Ending\u2026" : "End chat"}
      </Button>
    </div>
  );
}

function ChatModalContent({
  onCollapse,
}: {
  onCollapse: () => void;
}): JSX.Element {
  const backend = useSessionStore((s) => s.chat.backend);
  return (
    <div data-testid="chat-modal-content">
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: "var(--space-2)",
        }}
      >
        <Button
          variant="ghost"
          data-testid="chat-collapse-button"
          onClick={onCollapse}
        >
          Collapse
        </Button>
      </div>
      {backend === null ? <BackendPicker /> : <ActiveChat backend={backend} />}
      <ProposalPanel />
      <ReviewPanel />
      <GatePanel />
    </div>
  );
}

const MIN_CHAT_WIDTH = 360;
const MAX_CHAT_WIDTH = 720;
const DEFAULT_CHAT_WIDTH = 400;

export function ChatModal({ onClose }: ChatModalProps): JSX.Element {
  const [collapsed, setCollapsed] = useState(false);
  const [chatWidth, setChatWidth] = useState<number>(() => {
    try {
      const stored = localStorage.getItem("ef-panel-chat-width");
      const parsed = stored !== null ? Number(stored) : NaN;
      if (!Number.isFinite(parsed)) return DEFAULT_CHAT_WIDTH;
      return Math.min(MAX_CHAT_WIDTH, Math.max(MIN_CHAT_WIDTH, parsed));
    } catch {
      return DEFAULT_CHAT_WIDTH;
    }
  });
  const sessionId = useSessionStore((s) => s.sessionId);
  const status = useSessionStore((s) => s.status);
  const error = useSessionStore((s) => s.error);
  const createAndJoin = useSessionStore((s) => s.createAndJoin);
  const backend = useSessionStore((s) => s.chat.backend);
  const turns = useSessionStore((s) => s.chat.turns);
  const latestTurn = turns[turns.length - 1];
  // Guards against React StrictMode's synchronous double-invoke of this effect on mount,
  // which would otherwise fire createAndJoin() twice and orphan the first session -- the flag
  // is set before the async call starts and cleared once it settles, so a StrictMode replay
  // (which happens before the promise resolves) is skipped, but a later genuine retry (e.g.
  // status flipping to "error") is not permanently blocked.
  const autoCreateInFlight = useRef(false);

  useEffect(() => {
    if (
      sessionId === null &&
      status !== "connecting" &&
      !autoCreateInFlight.current
    ) {
      autoCreateInFlight.current = true;
      void createAndJoin().finally(() => {
        autoCreateInFlight.current = false;
      });
    }
  }, [sessionId, status, createAndJoin]);

  useEffect(() => {
    if (collapsed) return;
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, collapsed]);

  useEffect(() => {
    try {
      localStorage.setItem("ef-panel-chat-width", String(chatWidth));
    } catch {
      // ignore write errors
    }
  }, [chatWidth]);

  if (collapsed) {
    const label =
      backend === null
        ? "Chat"
        : latestTurn?.status === "running"
          ? `${backend} is working\u2026`
          : `${backend} chat`;
    return <ChatPill label={label} onExpand={() => setCollapsed(false)} />;
  }

  return (
    <div
      className="glass"
      data-testid="chat-dock"
      style={{
        position: "absolute",
        top: COMMAND_BAR_CLEARANCE,
        bottom: "var(--space-4)",
        right: "var(--space-4)",
        width: chatWidth,
        zIndex: 11,
        overflow: "auto",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        data-testid="chat-dock-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize chat panel"
        tabIndex={0}
        onKeyDown={(e) => {
          const step = 16;
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            setChatWidth((w) => Math.min(MAX_CHAT_WIDTH, w + step));
          } else if (e.key === "ArrowRight") {
            e.preventDefault();
            setChatWidth((w) => Math.max(MIN_CHAT_WIDTH, w - step));
          }
        }}
        onPointerDown={(e) => {
          const target = e.currentTarget;
          target.setPointerCapture(e.pointerId);
          const startX = e.clientX;
          const startWidth = chatWidth;
          function handlePointerMove(ev: PointerEvent): void {
            const delta = startX - ev.clientX;
            const next = Math.min(
              MAX_CHAT_WIDTH,
              Math.max(MIN_CHAT_WIDTH, startWidth + delta),
            );
            setChatWidth(next);
          }
          function finishDrag(ev: PointerEvent): void {
            target.releasePointerCapture(ev.pointerId);
            target.removeEventListener("pointermove", handlePointerMove);
            target.removeEventListener("pointerup", finishDrag);
            target.removeEventListener("pointercancel", finishDrag);
          }
          target.addEventListener("pointermove", handlePointerMove);
          target.addEventListener("pointerup", finishDrag);
          target.addEventListener("pointercancel", finishDrag);
        }}
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 6,
          cursor: "col-resize",
          background: "transparent",
          touchAction: "none",
        }}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          padding: "var(--space-1)",
        }}
      >
        <IconButton
          aria-label="Close chat"
          data-testid="chat-dock-close"
          onClick={onClose}
        >
          <X size={16} />
        </IconButton>
      </div>
      {sessionId === null ? (
        <div data-testid="chat-connecting">
          {status === "error" ? (
            <div style={{ color: "var(--danger)" }}>
              {error ?? "Failed to start a session."}
            </div>
          ) : (
            <p style={{ color: "var(--text-secondary)" }}>
              Starting session&hellip;
            </p>
          )}
        </div>
      ) : (
        <ChatModalContent onCollapse={() => setCollapsed(true)} />
      )}
    </div>
  );
}
