// Colony Mind canvas entry point.
//
// The canvas is a pure consumer of the local server's HTTP contract (ADR 0013
// Decision 3): it talks to the server ONLY over fetch (/compile, /execute,
// /validate, /healthz) and never imports the Python package. The only artifacts
// that cross the ui <-> server boundary are the IR JSON Schema, the generated
// code string, and the rules-as-data artifact.

interface HealthResponse {
  status: string;
}

async function ping(): Promise<string> {
  const res = await fetch("/healthz");
  const body = (await res.json()) as HealthResponse;
  return body.status;
}

async function main(): Promise<void> {
  const app = document.getElementById("app");
  if (!app) {
    return;
  }
  app.textContent = "Colony Mind canvas — connecting…";
  try {
    const status = await ping();
    app.textContent = `Colony Mind canvas — server status: ${status}`;
  } catch (err) {
    app.textContent = `Colony Mind canvas — server unreachable: ${String(err)}`;
  }
}

void main();
