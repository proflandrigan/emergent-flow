import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useExecutionStore } from "../store/executionStore";
import type { Payload } from "../store/execution";
import { useSelectionStore } from "../store/selectionStore";
import { DataPanel } from "./DataPanel";
import { FrameBrowser } from "./FrameBrowser";

afterEach(() => {
  vi.restoreAllMocks();
});

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function okWindow(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    status: "ok",
    revision: "r1",
    columns: ["term", "n"],
    dtypes: ["object", "int64"],
    total_rows: 1200,
    filtered_rows: 1200,
    offset: 0,
    limit: 100,
    rows: [
      { term: "a", n: 1, _row: 0 },
      { term: "b", n: 2, _row: 1 },
    ],
    ...over,
  };
}

function mount(): void {
  render(
    <FrameBrowser nodeId="n1" portName="frame" revision="r1" columns={["term", "n"]} dtypes={["object", "int64"]} />,
  );
}

test("shows the window with Showing X-Y of total and sends the revision", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(reply(okWindow()));
  mount();
  await waitFor(() => expect(screen.getByTestId("browse-range").textContent).toContain("Showing 1–2 of 1,200"));
  expect(screen.getAllByTestId("browse-row")).toHaveLength(2);
  const sent = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
  expect(sent).toMatchObject({ node_id: "n1", port: "frame", revision: "r1", offset: 0, limit: 100 });
});

test("a filter edit is sent typed and the filtered count shows (of total)", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (_u, init) => {
    const body = JSON.parse((init as RequestInit).body as string);
    return reply(body.filters.length ? okWindow({ filtered_rows: 1, rows: [{ term: "x", n: 7, _row: 7 }] }) : okWindow());
  });
  mount();
  await waitFor(() => screen.getByTestId("browse-range"));
  fireEvent.click(screen.getByTestId("browse-add-filter"));
  fireEvent.change(screen.getByLabelText("Filter value"), { target: { value: "x" } });
  await waitFor(() => expect(screen.getByTestId("browse-range").textContent).toContain("of 1 (of 1,200)"));
  const last = JSON.parse((spy.mock.calls[spy.mock.calls.length - 1][1] as RequestInit).body as string);
  expect(last.filters).toEqual([{ column: "term", operator: "==", value: "x" }]);
});

test("click-to-sort header sends sort", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(reply(okWindow()));
  mount();
  await waitFor(() => screen.getByTestId("browse-range"));
  fireEvent.click(screen.getByTestId("browse-col-header-n"));
  await waitFor(() => {
    const last = JSON.parse((spy.mock.calls[spy.mock.calls.length - 1][1] as RequestInit).body as string);
    expect(last.sort).toEqual([{ column: "n", ascending: true }]);
  });
});

test.each(["expired", "revision_mismatch"])("%s shows the re-run message", async (status) => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(reply({ status, current_revision: "r2" }));
  mount();
  await waitFor(() => expect(screen.getByTestId("browse-replaced").textContent).toContain("Output replaced or evicted — re-run"));
  expect(screen.queryByTestId("browse-table")).toBeNull();
});

test("a stale slow response does not overwrite a newer one", async () => {
  let resolveFirst: (r: Response) => void = () => undefined;
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(() => {
    calls += 1;
    if (calls === 1) {
      return new Promise<Response>((r) => {
        resolveFirst = r;
      });
    }
    return Promise.resolve(reply(okWindow({ rows: [{ term: "new", n: 2, _row: 1 }] })));
  });
  mount();
  await waitFor(() => expect(calls).toBe(1));
  fireEvent.click(screen.getByTestId("browse-col-header-n"));
  await waitFor(() => expect(screen.getByText("new")).toBeTruthy());
  resolveFirst(reply(okWindow({ rows: [{ term: "old", n: 1, _row: 0 }] })));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByText("old")).toBeNull();
});

const tablePayload: Payload = {
  kind: "table",
  columns: ["term"],
  dtypes: ["object"],
  shape: [1200, 1],
  head: [{ term: "a" }, { term: "b" }],
  truncated: true,
};

beforeEach(() => {
  useExecutionStore.getState().clear();
  useSelectionStore.setState({ nodes: { n1: true }, edges: {} });
});

test("DataPanel without a revision shows the labelled preview", () => {
  useExecutionStore.getState().setNodeResult("n1", { frame: tablePayload });
  render(<DataPanel />);
  expect(screen.getByTestId("data-preview-label").textContent).toContain(
    "Preview — first 2 of 1200 rows; filter/sort apply to the preview only",
  );
  expect(screen.getByTestId("data-preview-counts").textContent).toContain("Showing 2 of 2 preview rows");
  expect(screen.queryByTestId("frame-browser")).toBeNull();
});

test("DataPanel with a revision mounts the full-frame browser", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(reply(okWindow()));
  useExecutionStore.getState().setNodeResult("n1", { frame: tablePayload }, "r1");
  render(<DataPanel />);
  expect(screen.getByTestId("frame-browser")).toBeTruthy();
  expect(screen.queryByTestId("data-preview-label")).toBeNull();
  await waitFor(() => screen.getByTestId("browse-range"));
});
