import { expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { ResolvedTourStep } from "../canvas/tourResolve";
import type { Tour } from "./sessionClient";
import { TourPlayer, type TourPlayerProps } from "./TourPlayer";

const tour: Tour = {
  id: "t",
  title: "My tour",
  conclusion: "The **answer**",
  author: "agent",
  steps: [
    { focus: ["a"], note: "first" },
    { focus: ["a"], reach: "both", note: "second" },
    { route: ["a", "b"], note: "third", unknowns: ["Why is b slow?"] },
  ],
};

function resolved(overrides: Partial<ResolvedTourStep> = {}): ResolvedTourStep {
  return {
    kind: "focus",
    authoredIds: [],
    removedIds: [],
    highlight: { active: false, highlightedNodeIds: new Set(), highlightedEdgeIds: new Set() },
    routeStatus: null,
    fitIds: [],
    ...overrides,
  };
}

function setup(props: Partial<TourPlayerProps> = {}) {
  const handlers = { onPrev: vi.fn(), onNext: vi.fn(), onExit: vi.fn() };
  const utils = render(
    <TourPlayer
      tour={tour}
      index={0}
      resolved={resolved()}
      nodeName={(id) => `name-${id}`}
      {...handlers}
      {...props}
    />,
  );
  return { ...handlers, ...utils };
}

test("first step shows conclusion, counter, disabled Prev, no open questions", () => {
  setup();
  expect(screen.getByTestId("tour-conclusion").textContent).toContain("The answer");
  expect(screen.getByTestId("tour-step-counter").textContent).toBe("Step 1/3");
  expect((screen.getByTestId("tour-prev") as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByTestId("tour-open-questions")).toBeNull();
});

test("last step shows open questions and disables Next", () => {
  setup({ index: 2 });
  expect(screen.getByTestId("tour-open-questions").textContent).toContain("Why is b slow?");
  expect((screen.getByTestId("tour-next") as HTMLButtonElement).disabled).toBe(true);
});

test("removed badge renders and note still shows", () => {
  setup({ resolved: resolved({ removedIds: ["gone"] }) });
  expect(screen.getByTestId("tour-removed-badge").textContent).toBe("Node removed: gone");
  expect(screen.getByTestId("tour-note").textContent).toContain("first");
});

test("no-path notice uses nodeName", () => {
  setup({ index: 2, resolved: resolved({ kind: "route", routeStatus: "no-path" }) });
  expect(screen.getByTestId("tour-no-path").textContent).toBe(
    "No directed path from name-a to name-b",
  );
});

test("markdown renders bold but not raw HTML or javascript links", () => {
  const evil: Tour = {
    ...tour,
    steps: [
      {
        note: "**bold** <img src=x onerror=alert(1)> [x](javascript:alert(1))",
      },
    ],
  };
  const { container } = setup({ tour: evil });
  expect(container.querySelector("strong")).not.toBeNull();
  expect(container.querySelector("img")).toBeNull();
  for (const a of Array.from(container.querySelectorAll("a"))) {
    expect(a.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
  }
});

test("buttons call callbacks", () => {
  const { onPrev, onNext, onExit } = setup({ index: 1 });
  fireEvent.click(screen.getByTestId("tour-prev"));
  fireEvent.click(screen.getByTestId("tour-next"));
  fireEvent.click(screen.getByTestId("tour-exit"));
  expect(onPrev).toHaveBeenCalled();
  expect(onNext).toHaveBeenCalled();
  expect(onExit).toHaveBeenCalled();
});
