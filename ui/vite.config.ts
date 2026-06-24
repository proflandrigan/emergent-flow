import { defineConfig } from "vite";

// The compiled canvas is bundled into the Python package's static directory
// (ADR 0013 Decision 1); the local `serve` command serves it. This is a build
// OUTPUT path, not a code import — the UI never imports the Python package.
export default defineConfig({
  build: {
    outDir: "../colonymind/_static",
    emptyOutDir: true,
  },
});
