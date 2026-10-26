import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { useTourStore } from "../store/tourStore";
import * as viewLinkStore from "../store/viewLinkStore";
import type { Tour } from "./sessionClient";
import { TourPanel } from "./TourPanel";
import { useSessionStore } from "./sessionStore";

vi.mock("../store/viewLinkStore", async () => {
  const actual = await vi.importActual<typeof import("../store/viewLinkStore")>(
    "../store/viewLinkStore",
  );
  return { ...actual, copyViewLink: vi.fn().mockResolvedValue("") };
});

function tour(id: string): Tour {
  return {
    id,
    title: `Tour ${id}`,
    conclusion: `Conclusion ${id}`,
    author: "agent",
    steps: [{ note: "n" }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useSessionStore.setState({ tours: {} });
  useTourStore.setState({ playing: null, start: vi.fn() });
});

test("shows empty state", () => {
  render(<TourPanel />);
  expect(screen.getByTestId("tour-empty")).toBeTruthy();
});

test("renders tours sorted by id", () => {
  useSessionStore.setState({ tours: { b: tour("b"), a: tour("a") } });
  render(<TourPanel />);
  const rows = screen.getAllByTestId("tour-row");
  expect(rows).toHaveLength(2);
  expect(rows[0]?.textContent).toContain("Tour a");
  expect(rows[1]?.textContent).toContain("Tour b");
});

test("Play starts the tour at 0 and calls onPlay", () => {
  const a = tour("a");
  useSessionStore.setState({ tours: { a } });
  const onPlay = vi.fn();
  render(<TourPanel onPlay={onPlay} />);
  fireEvent.click(screen.getByTestId("tour-play"));
  expect(useTourStore.getState().start).toHaveBeenCalledWith(a, 0);
  expect(onPlay).toHaveBeenCalled();
});

test("Copy link copies the tour link", () => {
  useSessionStore.setState({ tours: { a: tour("a") } });
  render(<TourPanel />);
  fireEvent.click(screen.getByTestId("tour-copy-link"));
  expect(viewLinkStore.copyViewLink).toHaveBeenCalledWith({ tour: "a", step: 0 });
});
