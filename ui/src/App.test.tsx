import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { getSession, type Tour } from "./session/sessionClient";
import { useSessionStore } from "./session/sessionStore";
import { useTourStore } from "./store/tourStore";
import { useViewLinkStore } from "./store/viewLinkStore";

vi.mock("./session/sessionClient", () => ({
  createSession: vi.fn().mockResolvedValue({
    id: "app-test-session",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
  }),
  getSession: vi.fn(),
  deleteSession: vi.fn(),
  replaceSessionGraph: vi.fn(),
  proposeMutation: vi.fn(),
  consultSession: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
  subscribeToSessionEvents: vi.fn(() => ({ close: vi.fn() })),
  createReview: vi.fn(),
  addReviewComment: vi.fn(),
  createGate: vi.fn(),
  closeGateRequest: vi.fn(),
  skipGateRequest: vi.fn(),
  postGateDecision: vi.fn(),
  startChat: vi.fn(),
  stopChatTurn: vi.fn(),
  endChat: vi.fn(),
  getAvailableAgents: vi.fn().mockResolvedValue([]),
}));

afterEach(() => {
  vi.clearAllMocks();
  useTourStore.getState().exit({ restore: false });
  useTourStore.setState({
    playing: null,
    snapshot: null,
    pendingViewportRestore: null,
    announcement: null,
  });
  useSessionStore.setState({
    sessionId: null,
    version: null,
    proposals: {},
    reviews: {},
    gates: {},
    tours: {},
    chat: { backend: null, backend_thread_id: null, active_persona: null, turns: [] },
    status: "idle",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
  useViewLinkStore.setState({
    pendingCanvas: null,
    pendingProposal: null,
    pendingReview: null,
    pendingTour: null,
    notice: null,
    fallbackUrl: null,
  });
  window.history.replaceState(null, "", "/");
});

// App fires two fetches on mount (/healthz and the palette's /catalog). A `Response` body is
// single-use, so the mock must return a FRESH response per call (and route by URL) — a shared
// mockResolvedValue(Response) would let whichever fetch reads second hit "body already read".
function mockHealth(status: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    let body: unknown;
    if (url.includes("/catalog")) {
      body = { nodes: [] };
    } else if (url.includes("/connections")) {
      body = { connections: [] };
    } else if (url.includes("/examples")) {
      body = { examples: [] };
    } else if (url.includes("/flows")) {
      body = { flows: [] };
    } else {
      body = { status };
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
}

function mockHealthWithExamples(status: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    let body: unknown;
    if (url.includes("/catalog")) {
      body = { nodes: [] };
    } else if (url.includes("/connections")) {
      body = { connections: [] };
    } else if (url.includes("/examples")) {
      body = {
        examples: [
          {
            path: "examples/iris",
            slug: "iris",
            name: "Iris classification",
          },
        ],
      };
    } else if (url.includes("/flows")) {
      body = { flows: [] };
    } else {
      body = { status };
    }
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

test("does not show the Get started gallery on mount", async () => {
  mockHealthWithExamples("ok");
  render(<App />);

  await waitFor(() => {
    expect(screen.queryByTestId("example-iris")).not.toBeInTheDocument();
  });
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

test("Browse schema overflow item opens the schema browser panel", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Browse schema"));

  await waitFor(() => {
    expect(screen.getByTestId("schema-no-connection")).toBeInTheDocument();
  });
});

test("the overflow menu closes on outside click and on Escape", async () => {
  mockHealth("ok");
  render(<App />);

  const toggle = screen.getByRole("button", { name: "More actions" });

  fireEvent.click(toggle);
  expect(screen.getByRole("menu")).toBeInTheDocument();

  // The outside-click listener attaches on the next tick (App.tsx) so the click that just
  // opened the menu doesn't bubble into it and immediately close what it opened -- let that
  // tick pass before simulating a click elsewhere.
  await new Promise((resolve) => setTimeout(resolve, 0));

  fireEvent.click(document.body);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  fireEvent.click(toggle);
  expect(screen.getByRole("menu")).toBeInTheDocument();

  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("Manage connections overflow item opens the connections panel", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Manage connections"));

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
});

test("Review proposals overflow item opens the proposals panel", async () => {
  mockHealth("ok");
  useSessionStore.setState({
    sessionId: "app-test-session",
    version: 0,
    proposals: {
      p1: {
        id: "p1",
        mutation: { base_version: 0, author: "ml_engineer", description: "add a describe node" },
        diagnostics: { diagnostics: [], edge_compatibility: {} },
        status: "pending",
      },
    },
  });
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Review proposals"));

  await waitFor(() => {
    expect(screen.getByTestId("proposal-panel")).toBeInTheDocument();
  });
});

test("Start chat overflow item opens the chat modal", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Start chat"));

  await waitFor(() => {
    expect(screen.getByTestId("chat-connecting")).toBeInTheDocument();
  });
  await waitFor(() => {
    expect(screen.getByTestId("chat-backend-picker")).toBeInTheDocument();
  });
});

test("applies #focus after joining ?session=", async () => {
  mockHealth("ok");
  window.history.replaceState(null, "", "/?session=s1#focus=n1");
  vi.mocked(getSession).mockResolvedValue({
    id: "s1",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
  } as never);
  render(<App />);

  await waitFor(() => expect(getSession).toHaveBeenCalledWith("s1"));
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/node "n1"/),
  );
  // The hash stays in the URL (Back/Forward and refresh keep the view), as does ?session=.
  expect(window.location.hash).toBe("#focus=n1");
  expect(window.location.search).toBe("?session=s1");
});

test("#proposal opens the proposals panel highlighted", async () => {
  mockHealth("ok");
  window.history.replaceState(null, "", "/?session=s1#proposal=p1");
  vi.mocked(getSession).mockResolvedValue({
    id: "s1",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {
      p1: {
        id: "p1",
        mutation: { base_version: 0, author: "ml_engineer", description: "add a describe node" },
        diagnostics: { diagnostics: [], edge_compatibility: {} },
        status: "pending",
      },
    },
  } as never);
  render(<App />);

  const panel = await screen.findByTestId("proposal-panel");
  await waitFor(() =>
    expect(panel.querySelector('[data-highlighted="true"]')).not.toBeNull(),
  );
});

test("hashchange re-applies the view", async () => {
  mockHealth("ok");
  render(<App />);

  window.history.replaceState(null, "", "/#review=r9");
  window.dispatchEvent(new HashChangeEvent("hashchange"));

  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r9"/),
  );
});

// jsdom queues an anchor's fragment navigation as a task, so let it settle inside the test --
// otherwise a late hashchange leaks into the next test.
async function clickLink(href: string, init: MouseEventInit = {}): Promise<void> {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = "link";
  document.body.appendChild(a);
  fireEvent.click(a, init);
  a.remove();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

test("clicking a link to the current hash re-applies it", async () => {
  mockHealth("ok");
  render(<App />);

  window.location.hash = "#review=r9";
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r9"/),
  );
  expect(window.location.hash).toBe("#review=r9");

  // Browsers fire no hashchange for the identical fragment; the delegated click handler re-applies.
  useViewLinkStore.getState().setNotice(null);
  await clickLink("#review=r9");
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r9"/),
  );

  // Modified clicks open elsewhere (new tab/window) and leave this view alone.
  useViewLinkStore.getState().setNotice(null);
  await clickLink("#review=r9", { ctrlKey: true });
  expect(useViewLinkStore.getState().notice).toBeNull();
});

test("a link to a different hash is applied once (by hashchange only)", async () => {
  mockHealth("ok");
  render(<App />);
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  await clickLink("#review=r7");
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r7"/),
  );
  expect(request).toHaveBeenCalledTimes(1);
  request.mockRestore();
});

test("Back re-applies the previous deep-link view", async () => {
  mockHealth("ok");
  render(<App />);

  window.location.hash = "#review=r1";
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r1"/),
  );
  window.location.hash = "#review=r2";
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r2"/),
  );

  useViewLinkStore.getState().setNotice(null);
  window.history.back();
  await waitFor(() => expect(window.location.hash).toBe("#review=r1"));
  await waitFor(() =>
    expect(useViewLinkStore.getState().notice ?? "").toMatch(/review "r1"/),
  );
});

test("a view_url for the active session is applied in place after an in-app join", async () => {
  mockHealth("ok");
  render(<App />);
  // Start chat -> createAndJoin(): the session is joined but the address bar has no ?session=.
  await useSessionStore.getState().createAndJoin();
  expect(window.location.search).toBe("");
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  // The shape build_view_url emits: <base>/?session=<id>#focus=...
  const a = document.createElement("a");
  a.href = `${window.location.origin}/?session=app-test-session#focus=n1`;
  document.body.appendChild(a);
  const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
  a.dispatchEvent(click);
  a.remove();
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(click.defaultPrevented).toBe(true); // no full-page navigation
  expect(request).toHaveBeenCalledTimes(1);
  expect(request.mock.calls[0][0].focus).toEqual(["n1"]);
  expect(window.location.search).toBe("?session=app-test-session");
  expect(window.location.hash).toBe("#focus=n1");

  // Back returns to the pre-push entry (no hash): an empty view, which request() ignores.
  window.history.back();
  await waitFor(() => expect(window.location.search).toBe(""));
  expect(useSessionStore.getState().sessionId).toBe("app-test-session");
  request.mockRestore();
});

test("a view_url for a different session keeps normal navigation", async () => {
  mockHealth("ok");
  render(<App />);
  await useSessionStore.getState().createAndJoin();
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  const a = document.createElement("a");
  a.href = `${window.location.origin}/?session=other-session#focus=n1`;
  document.body.appendChild(a);
  const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
  // Runs after App's listener: record whether App cancelled it, then cancel so jsdom doesn't
  // attempt (and log) the cross-document navigation a browser would perform.
  let preventedByApp: boolean | null = null;
  document.addEventListener(
    "click",
    (e) => {
      preventedByApp = e.defaultPrevented;
      e.preventDefault();
    },
    { once: true },
  );
  a.dispatchEvent(click);
  a.remove();

  expect(preventedByApp).toBe(false);
  expect(request).not.toHaveBeenCalled();
  expect(window.location.search).toBe("");
  request.mockRestore();
});

// The expanded chat renders inside OverlayModal, whose panel stops click propagation -- App's
// delegated link listener must still see clicks on agent links there.
async function openExpandedChatWithViewLink() {
  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Open chat"));
  useSessionStore.setState({
    chat: {
      backend: "claude",
      backend_thread_id: null,
      active_persona: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "add a node",
          narration: [],
          agent_message: `Done: [view it](${window.location.origin}/?session=app-test-session#focus=n1)`,
          status: "completed",
          error: null,
        },
      ],
    },
  } as never);
  await waitFor(() => expect(screen.getByText("view it")).toBeInTheDocument());
  fireEvent.click(screen.getByTestId("chat-dock-expand"));
  await waitFor(() => expect(screen.getByTestId("chat-expanded")).toBeInTheDocument());
  return screen.getByText("view it").closest("a")!;
}

test("an active-session view_url in the expanded chat overlay is applied in place", async () => {
  mockHealth("ok");
  render(<App />);
  await useSessionStore.getState().createAndJoin();
  expect(window.location.search).toBe("");
  const a = await openExpandedChatWithViewLink();
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
  a.dispatchEvent(click);
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(click.defaultPrevented).toBe(true); // no full-page navigation
  expect(request).toHaveBeenCalledTimes(1);
  expect(window.location.search).toBe("?session=app-test-session");
  expect(window.location.hash).toBe("#focus=n1");
  request.mockRestore();
});

test("re-clicking the current view link in the expanded chat overlay re-applies it", async () => {
  mockHealth("ok");
  render(<App />);
  await useSessionStore.getState().createAndJoin();
  window.history.replaceState(null, "", "/?session=app-test-session#focus=n1");
  const a = await openExpandedChatWithViewLink();
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(request).toHaveBeenCalledTimes(1);
  request.mockRestore();
});

// A click-applied view is deferred to a macrotask so React Flow's node click handler (which
// re-selects the clicked node) runs first and the linked focus wins.
test("a click-applied view is requested after the click dispatch, not synchronously", async () => {
  mockHealth("ok");
  render(<App />);
  await useSessionStore.getState().createAndJoin();
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  const a = document.createElement("a");
  a.href = `${window.location.origin}/?session=app-test-session#focus=n1`;
  document.body.appendChild(a);
  const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
  a.dispatchEvent(click);
  a.remove();

  expect(click.defaultPrevented).toBe(true); // preventDefault stays synchronous
  expect(window.location.hash).toBe("#focus=n1"); // so does pushState
  await Promise.resolve(); // a microtask is not enough
  expect(request).not.toHaveBeenCalled();

  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(request).toHaveBeenCalledTimes(1);
  expect(request.mock.calls[0][0].focus).toEqual(["n1"]);
  request.mockRestore();
});

test("unmounting before the deferred request fires drops it", async () => {
  mockHealth("ok");
  const { unmount } = render(<App />);
  window.history.replaceState(null, "", "/#focus=n1");
  const request = vi.spyOn(useViewLinkStore.getState(), "request");

  const a = document.createElement("a");
  a.href = "#focus=n1";
  document.body.appendChild(a);
  a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  a.remove();
  unmount();
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(request).not.toHaveBeenCalled();
  request.mockRestore();
});

test("bad keys never throw", () => {
  mockHealth("ok");
  window.history.replaceState(null, "", "/#nonsense=1&focus=%E0%A4%A");
  expect(() => render(<App />)).not.toThrow();
  expect(
    screen.getByRole("heading", { name: /Emergent Flow/ }),
  ).toBeInTheDocument();
});

test("Get started overflow item opens the gallery and close dismisses it", async () => {
  mockHealthWithExamples("ok");
  render(<App />);

  expect(screen.queryByTestId("gallery-close")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Get started" }));

  await waitFor(() => {
    expect(screen.getByTestId("example-iris")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("gallery-close"));
  await waitFor(() => {
    expect(screen.queryByTestId("example-iris")).not.toBeInTheDocument();
  });
});

const TOUR: Tour = {
  id: "t1",
  title: "Walkthrough",
  conclusion: "All **good**",
  author: "agent",
  steps: [
    { focus: ["n1"], note: "first" },
    { focus: ["n1"], reach: "both", note: "second" },
    { focus: ["n1"], note: "third" },
  ],
};

function mockTourSession(tours: Record<string, Tour> = { t1: TOUR }) {
  vi.mocked(getSession).mockResolvedValue({
    id: "s1",
    graph: {
      paradigm: "functional",
      nodes: {
        n1: {
          id: "n1",
          type: "data.load_csv",
          label: null,
          paradigm: "functional",
          position: { x: 0, y: 0 },
          params: [],
          ports: [],
          group_id: null,
        },
      },
      edges: {},
    },
    version: 0,
    proposals: {},
    collab: { tours },
  } as never);
}

async function playTourViaStore() {
  mockHealth("ok");
  useSessionStore.setState({ sessionId: "s1", status: "connected", tours: { t1: TOUR } });
  render(<App />);
  act(() => useTourStore.getState().start(TOUR, 0));
  await screen.findByTestId("tour-player");
}

test("Tours menu item opens the tour panel", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Tours"));

  await waitFor(() => {
    expect(screen.getByTestId("tour-empty")).toBeInTheDocument();
  });
});

test("#tour deep link starts playback after joining ?session=", async () => {
  mockHealth("ok");
  mockTourSession();
  window.history.replaceState(null, "", "/?session=s1#tour=t1&step=0");
  render(<App />);

  await waitFor(() => expect(useTourStore.getState().playing?.tour.id).toBe("t1"));
  expect(useTourStore.getState().playing?.index).toBe(0);
  expect(await screen.findByTestId("tour-player")).toBeInTheDocument();
});

test("#tour with an out-of-range step starts at 0 with a notice", async () => {
  mockHealth("ok");
  mockTourSession();
  window.history.replaceState(null, "", "/?session=s1#tour=t1&step=9");
  render(<App />);

  await waitFor(() => expect(useTourStore.getState().playing?.tour.id).toBe("t1"));
  expect(useTourStore.getState().playing?.index).toBe(0);
  expect(await screen.findByTestId("view-link-toast")).toHaveTextContent(/no step 9/);
});

test("unknown #tour shows a notice and does not play", async () => {
  mockHealth("ok");
  mockTourSession();
  window.history.replaceState(null, "", "/?session=s1#tour=nope");
  render(<App />);

  expect(await screen.findByTestId("view-link-toast")).toHaveTextContent(/tour "nope"/);
  expect(useTourStore.getState().playing).toBeNull();
});

test("ArrowRight/ArrowLeft/Escape drive playback", async () => {
  await playTourViaStore();

  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(useTourStore.getState().playing?.index).toBe(1);
  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(useTourStore.getState().playing?.index).toBe(0);

  const input = document.createElement("input");
  document.body.appendChild(input);
  fireEvent.keyDown(input, { key: "ArrowRight" });
  input.remove();
  expect(useTourStore.getState().playing?.index).toBe(0);

  fireEvent.keyDown(window, { key: "Escape" });
  expect(useTourStore.getState().playing).toBeNull();
});

test("a remote tour delete exits playback", async () => {
  await playTourViaStore();

  act(() => useSessionStore.setState({ tours: {} }));

  await waitFor(() => expect(useTourStore.getState().playing).toBeNull());
  expect(useViewLinkStore.getState().notice).toBe("Tour deleted");
});

test("Escape closes a modal opened over a playing tour without exiting the tour", async () => {
  await playTourViaStore();

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Tours"));
  const dialog = await screen.findByRole("dialog");

  fireEvent.keyDown(dialog, { key: "Escape" });

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(useTourStore.getState().playing?.tour.id).toBe("t1");
});
