import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { OpenQuestionBadge } from "./OpenQuestionBadge";

test("renders the default label", () => {
  render(<OpenQuestionBadge />);
  expect(screen.getByTestId("open-question-badge").textContent).toContain("Open question");
});

test("renders a custom label", () => {
  render(<OpenQuestionBadge label="Open questions" />);
  expect(screen.getByTestId("open-question-badge").textContent).toContain("Open questions");
});

test("the ? mark is aria-hidden", () => {
  render(<OpenQuestionBadge />);
  const mark = screen.getByText("?");
  expect(mark.getAttribute("aria-hidden")).toBe("true");
});
