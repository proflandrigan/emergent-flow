import { lazy, Suspense, useEffect, useState } from "react";
import {
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Redo2,
  Undo2,
} from "lucide-react";

import { Canvas } from "./canvas/Canvas";
import { ConnectionManagerPanel } from "./connections/ConnectionManagerPanel";
import { SchemaBrowserPanel } from "./connections/SchemaBrowserPanel";
import { RunsPanel } from "./execution/RunsPanel";
import { getDevMenuItems } from "./dev/DevControls";
import { ExecutionToolbar } from "./exec/ExecutionToolbar";
import { Inspector } from "./inspector/Inspector";
import { ExampleGallery } from "./io/ExampleGallery";
import { useFlowStore, startDirtyTracking } from "./io/flowStore";
import { IRToolbar } from "./io/IRToolbar";
import {
  clearSession,
  recoverSession,
  useSessionAutoSave,
} from "./io/sessionRecovery";
import { Palette } from "./palette/Palette";
import { useGraphStore } from "./store/graphStore";
import { useSessionStore } from "./session/sessionStore";
import { useTheme } from "./theme/useTheme";
import { IconButton } from "./ui/IconButton";
import { Menu, type MenuItem } from "./ui/Menu";
import { OverlayModal } from "./ui/OverlayModal";
import { ResizeHandle } from "./ui/ResizeHandle";
import { Toast } from "./ui/Toast";
import { Tooltip } from "./ui/Tooltip";

// Lazy: nothing under ui/src/session/ is imported until the user opens this modal (Epic 14
// works-without-agents invariant -- chat mode is strictly opt-in, App's default render path
// stays byte-identical to before this epic).
const ChatModal = lazy(() =>
  import("./session/ChatModal").then((m) => ({ default: m.ChatModal })),
);

type ServerStatus = "connecting" | "ok" | "unreachable";

interface HealthResponse {
  status: string;
}

const STATUS_COLOR: Record<ServerStatus, string> = {
  ok: "var(--success)",
  connecting: "var(--warning)",
  unreachable: "var(--danger)",
};

// Estimated single-row height of the floating command bar (32px button row + --space-2
// vertical padding on each side); panels below it use this to clear the bar with a gutter
// gap, per spec `calc(100vh - 2*gutter - commandbar)`.
export const COMMAND_BAR_CLEARANCE = "calc(var(--space-4) * 2 + 56px)";

// Inspector dock sizing. The floor keeps the Config form's labelled fields legible; the
// ceiling keeps the canvas usable on a laptop display. DEFAULT is the width the dock
// shipped with, and is what double-click / Home on the drag handle restores.
const MIN_INSPECTOR_WIDTH = 280;
const MAX_INSPECTOR_WIDTH = 720;
const DEFAULT_INSPECTOR_WIDTH = 320;

function clampInspectorWidth(width: number): number {
  return Math.min(
    MAX_INSPECTOR_WIDTH,
    Math.max(MIN_INSPECTOR_WIDTH, Math.round(width)),
  );
}

function Divider(): JSX.Element {
  return (
    <div
      style={{
        width: 1,
        alignSelf: "stretch",
        background: "var(--border-subtle)",
      }}
    />
  );
}

export function App(): JSX.Element {
  const [status, setStatus] = useState<ServerStatus>("connecting");
  const [menuOpen, setMenuOpen] = useState(false);
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [schemaBrowserOpen, setSchemaBrowserOpen] = useState(false);
  const [runsOpen, setRunsOpen] = useState(false);
  const [chatModalOpen, setChatModalOpen] = useState(false);
  const [recoveryToast, setRecoveryToast] = useState<string | null>(null);
  const past = useGraphStore((s) => s.past);
  const future = useGraphStore((s) => s.future);
  const sessionId = useSessionStore((s) => s.sessionId);
  const canUndo = past.length > 0;
  const canRedo = future.length > 0;
  const { theme, toggleTheme } = useTheme();

  useSessionAutoSave();

  const [paletteCollapsed, setPaletteCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("ef-panel-palette-collapsed") === "true";
    } catch {
      return false;
    }
  });

  const [inspectorCollapsed, setInspectorCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("ef-panel-inspector-collapsed") === "true";
    } catch {
      return false;
    }
  });

  const [inspectorWidth, setInspectorWidth] = useState<number>(() => {
    try {
      const stored = Number(
        localStorage.getItem("ef-panel-inspector-width") ?? "",
      );
      return Number.isFinite(stored) && stored > 0
        ? clampInspectorWidth(stored)
        : DEFAULT_INSPECTOR_WIDTH;
    } catch {
      return DEFAULT_INSPECTOR_WIDTH;
    }
  });

  const [resizingInspector, setResizingInspector] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(
        "ef-panel-palette-collapsed",
        String(paletteCollapsed),
      );
    } catch {
      // ignore write errors
    }
  }, [paletteCollapsed]);

  useEffect(() => {
    try {
      localStorage.setItem(
        "ef-panel-inspector-collapsed",
        String(inspectorCollapsed),
      );
    } catch {
      // ignore write errors
    }
  }, [inspectorCollapsed]);

  useEffect(() => {
    try {
      localStorage.setItem("ef-panel-inspector-width", String(inspectorWidth));
    } catch {
      // ignore write errors
    }
  }, [inspectorWidth]);

  useEffect(() => {
    if (!menuOpen && !connectionsOpen && !schemaBrowserOpen && !runsOpen) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setConnectionsOpen(false);
        setSchemaBrowserOpen(false);
        setRunsOpen(false);
      }
    }
    function onClick() {
      setMenuOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    // Deferred via setTimeout: the click that just set menuOpen/etc. to true is still
    // bubbling up to document when this effect's passive-effect flush runs (React commits
    // discrete updates synchronously for real native events), so attaching this listener
    // synchronously would catch that SAME click and immediately close what it just opened.
    // Pushing the attach to the next task lets the triggering click finish bubbling first.
    const timer = window.setTimeout(() => {
      document.addEventListener("click", onClick);
    }, 0);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(timer);
      document.removeEventListener("click", onClick);
    };
  }, [menuOpen, connectionsOpen, schemaBrowserOpen, runsOpen]);

  useEffect(() => {
    let cancelled = false;
    fetch("/healthz")
      .then((res) => res.json() as Promise<HealthResponse>)
      .then((body) => {
        if (!cancelled) {
          setStatus(body.status === "ok" ? "ok" : "unreachable");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("unreachable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Runs once on mount: start tracking canvas-dirty state, warm the examples list, and
  // recover any localStorage-persisted session left behind by a refresh/crash -- or, if the
  // URL carries a ?session=<id>, join that collaboration session instead (the agent-driven
  // MCP workflow) so the human lands directly on the shared graph.
  useEffect(() => {
    startDirtyTracking();
    useFlowStore.getState().fetchExamples();
    const urlSession = new URLSearchParams(window.location.search).get("session");
    if (urlSession) {
      void useSessionStore.getState().join(urlSession);
      return;
    }
    const recovered = recoverSession();
    if (recovered) {
      useGraphStore.getState().loadIR(recovered.graph);
      setRecoveryToast("Recovered unsaved flow");
      clearSession();
    }
  }, []);

  // Warn on tab close / refresh while there are unsaved changes.
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (useFlowStore.getState().isDirty) {
        e.preventDefault();
      }
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, []);

  useEffect(() => {
    function isTextEntryTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      return (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      );
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) {
        return;
      }
      // Let native undo/redo work in text fields (e.g. the palette search box) instead of
      // hijacking it for canvas undo/redo -- the two stacks are unrelated.
      if (isTextEntryTarget(e.target)) {
        return;
      }
      const key = e.key.toLowerCase();
      if (key === "z" && e.shiftKey) {
        e.preventDefault();
        useGraphStore.getState().redo();
      } else if (key === "z") {
        e.preventDefault();
        useGraphStore.getState().undo();
      } else if (key === "y") {
        e.preventDefault();
        useGraphStore.getState().redo();
      } else if (key === "s") {
        e.preventDefault();
        const { currentSlug } = useFlowStore.getState();
        if (currentSlug) {
          const graph = useGraphStore.getState().toIR();
          useFlowStore.getState().saveFlow(currentSlug, graph);
        }
        // No currentSlug yet: leave it to the toolbar's File > Save As, which
        // prompts for a name -- a keyboard shortcut shouldn't pop a prompt().
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const overflowItems: MenuItem[] = [
    {
      label:
        theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
      onSelect: () => {
        toggleTheme();
        setMenuOpen(false);
      },
    },
    {
      label: "Manage connections",
      onSelect: () => {
        setConnectionsOpen(true);
        setMenuOpen(false);
      },
    },
    {
      label: "Browse schema",
      onSelect: () => {
        setSchemaBrowserOpen(true);
        setMenuOpen(false);
      },
    },
    {
      label: "Run history",
      onSelect: () => {
        setRunsOpen(true);
        setMenuOpen(false);
      },
    },
    {
      label: sessionId !== null ? "Open chat" : "Start chat",
      onSelect: () => {
        setChatModalOpen(true);
        setMenuOpen(false);
      },
    },
    ...getDevMenuItems().map((item) => ({
      ...item,
      onSelect: () => {
        item.onSelect();
        setMenuOpen(false);
      },
    })),
  ];

  // Rendered either inside the Inspector's control row (open) or in the collapsed rail.
  const inspectorCollapseToggle = (
    <Tooltip label={inspectorCollapsed ? "Show inspector" : "Hide inspector"}>
      <IconButton
        aria-label={inspectorCollapsed ? "Show inspector" : "Hide inspector"}
        data-testid="inspector-collapse-toggle"
        onClick={() => setInspectorCollapsed((c) => !c)}
      >
        {inspectorCollapsed ? (
          <PanelRightOpen size={16} />
        ) : (
          <PanelRightClose size={16} />
        )}
      </IconButton>
    </Tooltip>
  );

  return (
    <div style={{ position: "relative", height: "100vh", overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
        <Canvas />
      </div>
      <ExampleGallery />

      <div
        className="glass"
        style={{
          position: "absolute",
          top: "var(--space-4)",
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          padding: "var(--space-2) var(--space-3)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
          }}
        >
          <h1
            style={{
              fontSize: "var(--text-lg)",
              fontWeight: 600,
              margin: 0,
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
            }}
          >
            Emergent Flow
          </h1>
          <Tooltip label={`Server: ${status}`}>
            <span
              data-testid="server-status"
              style={{ display: "inline-flex", alignItems: "center" }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: STATUS_COLOR[status],
                  display: "inline-block",
                }}
              />
              <span className="sr-only">{status}</span>
            </span>
          </Tooltip>
        </div>

        <Divider />

        <IRToolbar />

        <Divider />

        <ExecutionToolbar />

        <Divider />

        <div style={{ display: "inline-flex", gap: "var(--space-2)" }}>
          <IconButton
            aria-label="Undo"
            disabled={!canUndo}
            onClick={() => useGraphStore.getState().undo()}
          >
            <Undo2 size={16} />
          </IconButton>
          <IconButton
            aria-label="Redo"
            disabled={!canRedo}
            onClick={() => useGraphStore.getState().redo()}
          >
            <Redo2 size={16} />
          </IconButton>
        </div>

        <Divider />

        <div style={{ position: "relative" }}>
          <IconButton
            aria-label="More actions"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MoreHorizontal size={16} />
          </IconButton>
          {menuOpen && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                right: 0,
                marginTop: "var(--space-1)",
                zIndex: 20,
              }}
            >
              <Menu items={overflowItems} aria-label="More actions" />
            </div>
          )}
        </div>
      </div>

      <div
        className="glass"
        style={{
          position: "absolute",
          top: COMMAND_BAR_CLEARANCE,
          bottom: "var(--space-4)",
          left: "var(--space-4)",
          width: paletteCollapsed ? 48 : 264,
          zIndex: 10,
          overflow: "auto",
          transition: "width var(--motion-fast) var(--motion-ease)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            padding: "var(--space-1)",
          }}
        >
          <Tooltip
            label={paletteCollapsed ? "Expand palette" : "Collapse palette"}
          >
            <IconButton
              aria-label={
                paletteCollapsed ? "Expand palette" : "Collapse palette"
              }
              data-testid="palette-collapse-toggle"
              onClick={() => setPaletteCollapsed((c) => !c)}
            >
              {paletteCollapsed ? (
                <PanelLeftOpen size={16} />
              ) : (
                <PanelLeftClose size={16} />
              )}
            </IconButton>
          </Tooltip>
        </div>
        {!paletteCollapsed && <Palette />}
      </div>

      {!inspectorCollapsed && (
        <ResizeHandle
          dock="right"
          width={inspectorWidth}
          min={MIN_INSPECTOR_WIDTH}
          max={MAX_INSPECTOR_WIDTH}
          resetWidth={DEFAULT_INSPECTOR_WIDTH}
          onWidthChange={setInspectorWidth}
          onResizingChange={setResizingInspector}
          label="Resize inspector"
          testId="inspector-resize-handle"
          // Sibling of the dock rather than a child: the dock is `overflow: auto`, which
          // would clip a handle straddling its left edge.
          style={{
            top: COMMAND_BAR_CLEARANCE,
            bottom: "var(--space-4)",
            right: `calc(var(--space-4) + ${inspectorWidth}px - 4px)`,
            zIndex: 11,
          }}
        />
      )}

      <div
        className="glass"
        data-testid="inspector-dock"
        style={{
          position: "absolute",
          top: COMMAND_BAR_CLEARANCE,
          bottom: "var(--space-4)",
          right: "var(--space-4)",
          width: inspectorCollapsed ? 48 : inspectorWidth,
          zIndex: 10,
          overflow: "auto",
          // Animating width would make the dock lag a pointer drag, so the transition is
          // only in play for the collapse/expand toggle.
          transition: resizingInspector
            ? "none"
            : "width var(--motion-fast) var(--motion-ease)",
        }}
      >
        {inspectorCollapsed ? (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              padding: "var(--space-1)",
            }}
          >
            {inspectorCollapseToggle}
          </div>
        ) : (
          // The toggle is handed to the Inspector so the dock has one control row in its
          // top-right corner (expand + hide) instead of two stacked icon rows.
          <Inspector chrome={inspectorCollapseToggle} />
        )}
      </div>

      {connectionsOpen && (
        <OverlayModal width={480} onClose={() => setConnectionsOpen(false)}>
          <ConnectionManagerPanel />
        </OverlayModal>
      )}

      {schemaBrowserOpen && (
        <OverlayModal width={560} onClose={() => setSchemaBrowserOpen(false)}>
          <SchemaBrowserPanel />
        </OverlayModal>
      )}
      {runsOpen && (
        <OverlayModal width={600} onClose={() => setRunsOpen(false)}>
          <RunsPanel onClose={() => setRunsOpen(false)} />
        </OverlayModal>
      )}
      {chatModalOpen && (
        <Suspense fallback={<div>Loading…</div>}>
          <ChatModal onClose={() => setChatModalOpen(false)} />
        </Suspense>
      )}

      {recoveryToast && (
        <div
          style={{
            position: "fixed",
            bottom: "var(--space-4)",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 100,
          }}
        >
          <Toast
            message={recoveryToast}
            onDismiss={() => setRecoveryToast(null)}
          />
        </div>
      )}
    </div>
  );
}
