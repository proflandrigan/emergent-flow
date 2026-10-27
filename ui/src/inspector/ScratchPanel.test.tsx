import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { scratchKey, SCRATCH_TEMPLATE, useScratchStore } from "../store/scratchStore";
import { ScratchPanel } from "./ScratchPanel";

const CUSTOM_CODE_SPEC = {
  type: "script.custom_code",
  version: 1,
  family: "script",
  label: "Custom Code",
  paradigm: "functional",
  ports: [
    { name: "value", direction: "in", data_type: "any" },
    { name: "result", direction: "out", data_type: "any" },
  ],
  params: [{ name: "code", type_token: "str", default: "" }],
};

let sourceId = "";
const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function mockServer(runBody: unknown, status = 200) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
    String(url) === "/catalog"
      ? json({ catalog_version: 1, nodes: [CUSTOM_CODE_SPEC], estimators: [], charts: [] })
      : json(runBody, status),
  );
}

beforeEach(() => {
  useGraphStore.getState().reset();
  useScratchStore.setState({ drafts: {}, activeKey: null });
  sourceId = useGraphStore.getState().addNodeFromSpec(
    {
      type: "data.load_csv",
      version: 1,
      family: "data",
      label: "Load CSV",
      paradigm: "functional",
      ports: [{ name: "frame", direction: "out", data_type: "DataFrame" }],
      params: [],
    },
    { x: 0, y: 0 },
  );
  useScratchStore.getState().open(sourceId, "frame", "Load CSV", "abcdef0123");
});

afterEach(() => {
  vi.restoreAllMocks();
});

const key = (): string => scratchKey(sourceId, "frame");
const setCode = (code: string): void => useScratchStore.getState().setCode(key(), code);

test("starts from the template and shows what it is bound to", () => {
  mockServer({});
  render(<ScratchPanel />);
  expect(screen.getByTestId("scratch-bound").textContent).toContain("Load CSV / frame / abcdef01");
  expect(useScratchStore.getState().drafts[key()].code).toBe(SCRATCH_TEMPLATE);
});

test("Run posts the bound revision and renders the result and stdout", async () => {
  const fetchSpy = mockServer({
    status: "ok",
    revision: "abcdef0123",
    result: { kind: "scalar", value: 42 },
    stdout: "hello\n",
    stderr: "",
    elapsed_ms: 1,
  });
  render(<ScratchPanel />);
  fireEvent.click(screen.getByTestId("scratch-run"));
  await waitFor(() => expect(screen.getByTestId("scratch-result")).toBeTruthy());
  expect(screen.getByTestId("scratch-stdout").textContent).toBe("hello\n");
  const call = fetchSpy.mock.calls.find((c) => String(c[0]) === "/scratch/run");
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({
    node_id: sourceId,
    port: "frame",
    revision: "abcdef0123",
    code: SCRATCH_TEMPLATE,
  });
});

test("an error shows type, message and line", async () => {
  mockServer({
    status: "error",
    revision: "abcdef0123",
    stdout: "",
    stderr: "",
    error: { type: "KeyError", message: "'nope'", traceback: "Traceback...", line: 3 },
  });
  render(<ScratchPanel />);
  fireEvent.click(screen.getByTestId("scratch-run"));
  const box = await screen.findByTestId("scratch-error");
  expect(box.textContent).toContain("KeyError (line 3)");
  expect(box.textContent).toContain("'nope'");
});

test.each([
  ["expired", {}, /no longer stored/],
  ["revision_mismatch", { current_revision: "zzz" }, /re-run/],
])("%s tells the user to re-run and does not rebind", async (status, extra, text) => {
  mockServer({ status, revision: "abcdef0123", ...extra });
  render(<ScratchPanel />);
  fireEvent.click(screen.getByTestId("scratch-run"));
  expect((await screen.findByTestId("scratch-stale")).textContent).toMatch(text);
  expect(useScratchStore.getState().drafts[key()].revision).toBe("abcdef0123");
  expect((screen.getByTestId("scratch-save") as HTMLButtonElement).disabled).toBe(true);
});

test("Save as code node is blocked until the code has run and parsed", async () => {
  mockServer({
    status: "error",
    revision: "abcdef0123",
    error: { type: "CustomCodeError", message: "bad", traceback: "", line: 1 },
  });
  render(<ScratchPanel />);
  const save = screen.getByTestId("scratch-save") as HTMLButtonElement;
  expect(save.disabled).toBe(true);
  fireEvent.click(screen.getByTestId("scratch-run"));
  await screen.findByTestId("scratch-error");
  expect(save.disabled).toBe(true);
});

test("promote creates the code node and edge in ONE history step, then selects it", async () => {
  mockServer({ status: "ok", revision: "abcdef0123", result: { kind: "scalar", value: 1 } });
  const onDone = vi.fn();
  render(<ScratchPanel onDone={onDone} />);
  const code = "def transform(value):\n    return value.head()";
  act(() => setCode(code));
  fireEvent.click(screen.getByTestId("scratch-run"));
  await screen.findByTestId("scratch-result");
  const pastBefore = useGraphStore.getState().past.length;
  const save = screen.getByTestId("scratch-save") as HTMLButtonElement;
  await waitFor(() => expect(save.disabled).toBe(false));

  fireEvent.click(save);

  const g = useGraphStore.getState();
  const created = Object.values(g.nodes).find((n) => n.type === "script.custom_code");
  expect(created?.params.find((p) => p.name === "code")?.value).toBe(code);
  const edges = Object.values(g.edges);
  expect(edges).toHaveLength(1);
  expect(edges[0].source.node_id).toBe(sourceId);
  expect(edges[0].target.node_id).toBe(created?.id);
  expect(g.past.length).toBe(pastBefore + 1);
  g.undo();
  expect(Object.keys(useGraphStore.getState().nodes)).toEqual([sourceId]);
  expect(Object.keys(useGraphStore.getState().edges)).toHaveLength(0);
  expect(onDone).toHaveBeenCalled();
  expect(useScratchStore.getState().drafts[key()]).toBeUndefined();
});

test("Discard clears scratch state and leaves the graph untouched", () => {
  mockServer({});
  render(<ScratchPanel />);
  const before = useGraphStore.getState();
  fireEvent.click(screen.getByTestId("scratch-discard"));
  const after = useGraphStore.getState();
  expect(after.nodes).toBe(before.nodes);
  expect(after.edges).toBe(before.edges);
  expect(after.past).toBe(before.past);
  expect(useScratchStore.getState().drafts).toEqual({});
  expect(screen.getByTestId("scratch-empty")).toBeTruthy();
});
