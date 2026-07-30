import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { useFlowStore } from "./flowStore";

function resetStore() {
  useFlowStore.setState({
    currentSlug: null,
    isDirty: false,
    flows: [],
    examples: [],
    loading: false,
    error: null,
  });
}

describe("flowStore", () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    resetStore();
  });

  test("starts with no current slug and clean state", () => {
    const state = useFlowStore.getState();
    expect(state.currentSlug).toBeNull();
    expect(state.isDirty).toBe(false);
    expect(state.flows).toEqual([]);
    expect(state.examples).toEqual([]);
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });

  test("setCurrentSlug updates the slug", () => {
    useFlowStore.getState().setCurrentSlug("my-flow");
    expect(useFlowStore.getState().currentSlug).toBe("my-flow");
  });

  test("setDirty marks the store dirty", () => {
    useFlowStore.getState().setDirty(true);
    expect(useFlowStore.getState().isDirty).toBe(true);
  });

  test("clearError resets error to null", () => {
    useFlowStore.setState({ error: "something broke" });
    useFlowStore.getState().clearError();
    expect(useFlowStore.getState().error).toBeNull();
  });

  describe("fetchFlows", () => {
    test("populates flows from the server", async () => {
      const mockFlows = [
        { slug: "a", name: "Alpha", updated_at: "2026-01-01T00:00:00Z" },
      ];
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ flows: mockFlows }),
        }),
      );
      await useFlowStore.getState().fetchFlows();
      expect(useFlowStore.getState().flows).toEqual(mockFlows);
      expect(useFlowStore.getState().loading).toBe(false);
      expect(useFlowStore.getState().error).toBeNull();
    });

    test("sets error on rejected fetch", async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
      await useFlowStore.getState().fetchFlows();
      expect(useFlowStore.getState().error).toBe("network");
      expect(useFlowStore.getState().loading).toBe(false);
    });

    test("sets error on a non-ok response", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ ok: false, status: 500 }),
      );
      await useFlowStore.getState().fetchFlows();
      expect(useFlowStore.getState().error).toContain("500");
    });
  });

  describe("fetchExamples", () => {
    test("populates examples from the server", async () => {
      const mockExamples = [{ name: "Demo", path: "demo.json", slug: "demo" }];
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ examples: mockExamples }),
        }),
      );
      await useFlowStore.getState().fetchExamples();
      expect(useFlowStore.getState().examples).toEqual(mockExamples);
    });

    test("fails silently on a non-ok response", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ ok: false, status: 404 }),
      );
      await useFlowStore.getState().fetchExamples();
      expect(useFlowStore.getState().examples).toEqual([]);
      expect(useFlowStore.getState().error).toBeNull();
    });

    test("fails silently on a network error", async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
      await expect(useFlowStore.getState().fetchExamples()).resolves.toBeUndefined();
      expect(useFlowStore.getState().error).toBeNull();
    });
  });

  describe("saveFlow", () => {
    test("clears dirty and refreshes the flow list on success", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) }) // PUT
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ flows: [] }),
        }); // fetchFlows refresh
      vi.stubGlobal("fetch", fetchMock);
      useFlowStore.setState({ isDirty: true });
      await useFlowStore.getState().saveFlow("my-flow", { nodes: {}, edges: {} });
      // saveFlow fires fetchFlows() without awaiting it — flush that microtask
      await new Promise((r) => setTimeout(r, 0));
      expect(useFlowStore.getState().isDirty).toBe(false);
      expect(useFlowStore.getState().loading).toBe(false);
      expect(fetchMock).toHaveBeenCalledWith(
        "/flows/my-flow",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    test("sets error message from the response body on failure", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ error: "bad graph" }),
        }),
      );
      await useFlowStore.getState().saveFlow("my-flow", { nodes: {}, edges: {} });
      expect(useFlowStore.getState().error).toBe("bad graph");
      expect(useFlowStore.getState().loading).toBe(false);
    });
  });

  describe("saveNewFlow", () => {
    test("sets currentSlug and returns the new slug on success", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ slug: "new-flow" }),
        }) // POST
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ flows: [] }),
        }); // fetchFlows refresh
      vi.stubGlobal("fetch", fetchMock);
      const slug = await useFlowStore
        .getState()
        .saveNewFlow("New Flow", { nodes: {}, edges: {} });
      expect(slug).toBe("new-flow");
      expect(useFlowStore.getState().currentSlug).toBe("new-flow");
      expect(useFlowStore.getState().isDirty).toBe(false);
    });

    test("rejects and sets error on failure", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ error: "name taken" }),
        }),
      );
      await expect(
        useFlowStore.getState().saveNewFlow("New Flow", { nodes: {}, edges: {} }),
      ).rejects.toThrow("name taken");
      expect(useFlowStore.getState().error).toBe("name taken");
    });
  });

  describe("loadFlow", () => {
    test("sets currentSlug and returns the graph on success", async () => {
      const graph = { nodes: { n1: {} }, edges: {} };
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(graph) }),
      );
      const result = await useFlowStore.getState().loadFlow("my-flow");
      expect(result).toEqual(graph);
      expect(useFlowStore.getState().currentSlug).toBe("my-flow");
      expect(useFlowStore.getState().isDirty).toBe(false);
    });

    test("rejects and sets error on failure", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ error: "not found" }),
        }),
      );
      await expect(useFlowStore.getState().loadFlow("missing")).rejects.toThrow(
        "not found",
      );
      expect(useFlowStore.getState().error).toBe("not found");
    });
  });

  describe("deleteFlow", () => {
    test("clears currentSlug when deleting the active flow", async () => {
      useFlowStore.setState({ currentSlug: "my-flow" });
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) }) // DELETE
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ flows: [] }),
        }); // fetchFlows refresh
      vi.stubGlobal("fetch", fetchMock);
      await useFlowStore.getState().deleteFlow("my-flow");
      expect(useFlowStore.getState().currentSlug).toBeNull();
    });

    test("leaves currentSlug untouched when deleting a different flow", async () => {
      useFlowStore.setState({ currentSlug: "other-flow" });
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ flows: [] }),
        });
      vi.stubGlobal("fetch", fetchMock);
      await useFlowStore.getState().deleteFlow("my-flow");
      expect(useFlowStore.getState().currentSlug).toBe("other-flow");
    });
  });

  describe("renameFlow", () => {
    test("updates currentSlug when renaming the active flow", async () => {
      useFlowStore.setState({ currentSlug: "old-slug" });
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ slug: "new-slug" }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ flows: [] }),
        });
      vi.stubGlobal("fetch", fetchMock);
      await useFlowStore.getState().renameFlow("old-slug", "new-slug");
      expect(useFlowStore.getState().currentSlug).toBe("new-slug");
    });

    // Regression test: renameFlow used to swallow a failed rename (catch without rethrow),
    // matching every OTHER mutating action except saveFlow/deleteFlow -- but unlike those,
    // IRToolbar's Rename… flow does more work after awaiting renameFlow (it renames the
    // in-memory graph too), so a caller must be able to tell success from failure.
    test("rejects and sets error on failure, matching saveNewFlow/loadFlow", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: false,
          status: 409,
          json: () => Promise.resolve({ error: "slug taken" }),
        }),
      );
      await expect(
        useFlowStore.getState().renameFlow("old-slug", "new-slug"),
      ).rejects.toThrow("slug taken");
      expect(useFlowStore.getState().error).toBe("slug taken");
    });
  });

  describe("loadExample", () => {
    test("marks the store dirty with no currentSlug on success", async () => {
      const graph = { nodes: { n1: {} }, edges: {} };
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(graph) }),
      );
      useFlowStore.setState({ currentSlug: "some-flow", isDirty: false });
      const result = await useFlowStore.getState().loadExample("demo.json");
      expect(result).toEqual(graph);
      expect(useFlowStore.getState().currentSlug).toBeNull();
      expect(useFlowStore.getState().isDirty).toBe(true);
    });

    test("rejects and sets error on failure", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
      await expect(useFlowStore.getState().loadExample("missing.json")).rejects.toThrow();
      expect(useFlowStore.getState().error).toBeTruthy();
    });
  });
});
