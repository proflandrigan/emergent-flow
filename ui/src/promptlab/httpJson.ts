// Shared POST-JSON-and-throw-on-error helper for the Prompt Lab's server calls
// (runEval.ts, exportDataset.ts), which all POST a JSON body to a server route and need the
// same non-2xx handling: parse `{"error": ...}` from the body if present, else fall back to
// the HTTP status. Returns the raw `Response` so callers can read it as JSON or as a blob.
export async function postJson(path: string, body: unknown): Promise<Response> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.error ?? `Server error ${res.status}`);
  }
  return res;
}
