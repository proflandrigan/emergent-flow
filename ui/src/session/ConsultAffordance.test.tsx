import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import * as sessionClient from "./sessionClient";
import { ConsultAffordance } from "./ConsultAffordance";
import { useSessionStore } from "./sessionStore";
import { usePersonas } from "./usePersonas";

vi.mock("./sessionClient", () => ({
  createSession: vi.fn(),
  getSession: vi.fn(),
  deleteSession: vi.fn(),
  replaceSessionGraph: vi.fn(),
  proposeMutation: vi.fn(),
  consultSession: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
  subscribeToSessionEvents: vi.fn(() => ({ close: vi.fn() })),
  createGate: vi.fn(),
  closeGateRequest: vi.fn(),
  skipGateRequest: vi.fn(),
  postGateDecision: vi.fn(),
}));

vi.mock("./usePersonas");

const knownPersonas = [
  {
    slug: "data_modeller",
    label: "Data Modeller",
    description: "Helps with data",
    node_families: ["data"],
  },
  {
    slug: "researcher",
    label: "Researcher",
    description: "Helps with research",
    node_families: ["stats"],
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(usePersonas).mockReturnValue(knownPersonas);
  useSessionStore.setState({
    sessionId: null,
    version: null,
    proposals: {},
    reviews: {},
    gates: {},
    status: "idle",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
});

test("renders nothing when there is no active session", () => {
  const { container } = render(
    <ConsultAffordance nodeId="n1" personaSlug="data_modeller" />,
  );
  expect(container).toBeEmptyDOMElement();
});

test("renders the Ask button when a session is active", () => {
  useSessionStore.setState({ sessionId: "abc" });

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  expect(screen.getByTestId("consult-affordance-open")).toHaveTextContent(
    "Ask Data Modeller",
  );
});

test("falls back to the raw slug when the persona is not found in resolved data", () => {
  useSessionStore.setState({ sessionId: "abc" });

  render(<ConsultAffordance nodeId="n1" personaSlug="unknown_persona" />);

  expect(screen.getByTestId("consult-affordance-open")).toHaveTextContent(
    "Ask unknown_persona",
  );
});

test("falls back to the raw slug when personas have not yet loaded", () => {
  vi.mocked(usePersonas).mockReturnValue([]);
  useSessionStore.setState({ sessionId: "abc" });

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  expect(screen.getByTestId("consult-affordance-open")).toHaveTextContent(
    "Ask data_modeller",
  );
});

test("clicking the Ask button reveals the form with textarea and submit/cancel buttons", () => {
  useSessionStore.setState({ sessionId: "abc" });

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  fireEvent.click(screen.getByTestId("consult-affordance-open"));

  expect(screen.getByTestId("consult-ask-input")).toBeInTheDocument();
  expect(screen.getByTestId("consult-submit")).toBeInTheDocument();
  expect(screen.getByTestId("consult-cancel")).toBeInTheDocument();
});

test("submit button is disabled when the textarea is empty", () => {
  useSessionStore.setState({ sessionId: "abc" });

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  fireEvent.click(screen.getByTestId("consult-affordance-open"));

  expect(screen.getByTestId("consult-submit")).toBeDisabled();
});

test("submit calls consultSession with the right params and collapses on success", async () => {
  useSessionStore.setState({ sessionId: "abc" });

  const proposal = {
    id: "p1",
    mutation: { base_version: 0 },
    diagnostics: { diagnostics: [], edge_compatibility: {} },
    status: "pending" as const,
  };
  vi.mocked(sessionClient.consultSession).mockResolvedValue(proposal);

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  fireEvent.click(screen.getByTestId("consult-affordance-open"));

  fireEvent.change(screen.getByTestId("consult-ask-input"), {
    target: { value: "analyze this data" },
  });

  fireEvent.click(screen.getByTestId("consult-submit"));

  await waitFor(() => {
    expect(sessionClient.consultSession).toHaveBeenCalledWith("abc", {
      persona: "data_modeller",
      node_ids: ["n1"],
      ask: "analyze this data",
    });
  });

  await waitFor(() => {
    expect(screen.queryByTestId("consult-ask-input")).not.toBeInTheDocument();
  });
  expect(screen.getByTestId("consult-affordance-open")).toBeInTheDocument();
});

test("cancel collapses without calling consultSession", () => {
  useSessionStore.setState({ sessionId: "abc" });

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  fireEvent.click(screen.getByTestId("consult-affordance-open"));
  fireEvent.change(screen.getByTestId("consult-ask-input"), {
    target: { value: "analyze this data" },
  });

  fireEvent.click(screen.getByTestId("consult-cancel"));

  expect(sessionClient.consultSession).not.toHaveBeenCalled();
  expect(screen.queryByTestId("consult-ask-input")).not.toBeInTheDocument();
  expect(screen.getByTestId("consult-affordance-open")).toBeInTheDocument();
});

test("a rejected consultSession shows the error and keeps the form open", async () => {
  useSessionStore.setState({ sessionId: "abc" });

  vi.mocked(sessionClient.consultSession).mockRejectedValue(
    new Error("server exploded"),
  );

  render(<ConsultAffordance nodeId="n1" personaSlug="data_modeller" />);

  fireEvent.click(screen.getByTestId("consult-affordance-open"));
  fireEvent.change(screen.getByTestId("consult-ask-input"), {
    target: { value: "analyze this data" },
  });

  fireEvent.click(screen.getByTestId("consult-submit"));

  await waitFor(() => {
    expect(screen.getByTestId("consult-error")).toHaveTextContent(
      "server exploded",
    );
  });

  // Form stays open so the user can retry
  expect(screen.getByTestId("consult-ask-input")).toBeInTheDocument();
  expect(
    screen.queryByTestId("consult-affordance-open"),
  ).not.toBeInTheDocument();
});
