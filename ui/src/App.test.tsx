import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

// App fires two fetches on mount (/healthz and the palette's /catalog). A `Response` body is
// single-use, so the mock must return a FRESH response per call (and route by URL) — a shared
// mockResolvedValue(Response) would let whichever fetch reads second hit "body already read".
function mockHealth(status: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    const body = url.includes("/catalog") ? { nodes: [] } : { status };
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
}

test("renders the canvas heading", () => {
  mockHealth("ok");
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /Emergent Flow/ }),
  ).toBeInTheDocument();
});

test("shows the server status as ok when /healthz is healthy", async () => {
  mockHealth("ok");
  render(<App />);
  await waitFor(() =>
    expect(screen.getByTestId("server-status")).toHaveTextContent("ok"),
  );
});

test("shows unreachable when the health request fails", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(
    new Error("connection refused"),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByTestId("server-status")).toHaveTextContent(
      "unreachable",
    ),
  );
});
