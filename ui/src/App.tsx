import { useEffect, useState } from "react";

import { Canvas } from "./canvas/Canvas";
import { Palette } from "./palette/Palette";
import { useGraphStore } from "./store/graphStore";

type ServerStatus = "connecting" | "ok" | "unreachable";

interface HealthResponse {
  status: string;
}

export function App(): JSX.Element {
  const [status, setStatus] = useState<ServerStatus>("connecting");
  const past = useGraphStore((s) => s.past);
  const future = useGraphStore((s) => s.future);
  const canUndo = past.length > 0;
  const canRedo = future.length > 0;

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
    function handleKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) {
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

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          padding: "0.5rem 1rem",
          borderBottom: "1px solid #ddd",
        }}
      >
        <h1 style={{ fontSize: "1rem", margin: 0 }}>Colony Mind — canvas</h1>
        <span
          data-testid="server-status"
          style={{ marginLeft: "1rem", color: "#666" }}
        >
          server: {status}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
          <button
            type="button"
            disabled={!canUndo}
            onClick={() => useGraphStore.getState().undo()}
          >
            Undo
          </button>
          <button
            type="button"
            disabled={!canRedo}
            onClick={() => useGraphStore.getState().redo()}
          >
            Redo
          </button>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        <Palette />
        <div style={{ flex: 1, minHeight: 0 }}>
          <Canvas />
        </div>
      </div>
    </div>
  );
}
