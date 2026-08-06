/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The local `emergentflow serve` server (ADR 0013) listens here in dev; the canvas talks to it
// ONLY over these HTTP routes and never imports the Python package.
const LOCAL_SERVER = "http://127.0.0.1:8765";
const SERVER_ROUTES = [
  "/healthz",
  "/schema",
  "/catalog",
  "/compile",
  "/compile-spec",
  "/validate",
  "/execute",
  "/execute_node",
  "/lineage",
  "/lineage/column",
  "/sessions",
  "/agents",
  "/consult",
  "/connections",
  "/reports",
  "/export",
  "/personas",
  "/knowledge",
  "/mutation-schema",
  "/session-event-schema",
];

export default defineConfig({
  plugins: [react()],
  // The compiled canvas is bundled into the Python package's static directory
  // (ADR 0013 Decision 1); the local `serve` command serves it. This is a build
  // OUTPUT path, not a code import -- the UI never imports the Python package.
  build: {
    outDir: "../emergentflow/_static",
    emptyOutDir: true,
  },
  server: {
    proxy: Object.fromEntries(
      SERVER_ROUTES.map((route) => [route, LOCAL_SERVER]),
    ),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
