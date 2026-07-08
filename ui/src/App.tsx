import { useEffect, useState } from "react";
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
import { getDevMenuItems } from "./dev/DevControls";
import { ExecutionToolbar } from "./exec/ExecutionToolbar";
import { Inspector } from "./inspector/Inspector";
import { IRToolbar } from "./io/IRToolbar";
import { Palette } from "./palette/Palette";
import { useGraphStore } from "./store/graphStore";
import { useTheme } from "./theme/useTheme";
import { IconButton } from "./ui/IconButton";
import { Menu, type MenuItem } from "./ui/Menu";
import { Tooltip } from "./ui/Tooltip";

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
const COMMAND_BAR_CLEARANCE = "calc(var(--space-4) * 2 + 56px)";

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
  const past = useGraphStore((s) => s.past);
  const future = useGraphStore((s) => s.future);
  const canUndo = past.length > 0;
  const canRedo = future.length > 0;
  const { theme, toggleTheme } = useTheme();

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

  useEffect(() => {
    try {
      localStorage.setItem("ef-panel-palette-collapsed", String(paletteCollapsed));
    } catch {
      // ignore write errors
    }
  }, [paletteCollapsed]);

  useEffect(() => {
    try {
      localStorage.setItem("ef-panel-inspector-collapsed", String(inspectorCollapsed));
    } catch {
      // ignore write errors
    }
  }, [inspectorCollapsed]);

  useEffect(() => {
    if (!menuOpen && !connectionsOpen && !schemaBrowserOpen) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setConnectionsOpen(false);
        setSchemaBrowserOpen(false);
      }
    }
    function onClick() {
      setMenuOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("click", onClick);
    };
  }, [menuOpen, connectionsOpen, schemaBrowserOpen]);

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
    ...getDevMenuItems().map((item) => ({
      ...item,
      onSelect: () => {
        item.onSelect();
        setMenuOpen(false);
      },
    })),
  ];

  return (
    <div style={{ position: "relative", height: "100vh", overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
        <Canvas />
      </div>

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

      <div
        className="glass"
        style={{
          position: "absolute",
          top: COMMAND_BAR_CLEARANCE,
          bottom: "var(--space-4)",
          right: "var(--space-4)",
          width: inspectorCollapsed ? 48 : 320,
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
            label={
              inspectorCollapsed ? "Expand inspector" : "Collapse inspector"
            }
          >
            <IconButton
              aria-label={
                inspectorCollapsed ? "Expand inspector" : "Collapse inspector"
              }
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
        </div>
        {!inspectorCollapsed && <Inspector />}
      </div>

      {connectionsOpen && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 30,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0, 0, 0, 0.4)",
          }}
          onClick={() => setConnectionsOpen(false)}
        >
          <div
            className="glass"
            style={{
              width: 480,
              maxHeight: "70vh",
              overflow: "auto",
              padding: "var(--space-4)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <ConnectionManagerPanel />
          </div>
        </div>
      )}

      {schemaBrowserOpen && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 30,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0, 0, 0, 0.4)",
          }}
          onClick={() => setSchemaBrowserOpen(false)}
        >
          <div
            className="glass"
            style={{
              width: 560,
              maxHeight: "70vh",
              overflow: "auto",
              padding: "var(--space-4)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <SchemaBrowserPanel />
          </div>
        </div>
      )}
    </div>
  );
}
