import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { ProblemsPanel } from "./ProblemsPanel";
import { useExecutionStore } from "../store/executionStore";
import { useSuppressionStore } from "../store/suppressionStore";
import { useValidationStore } from "../store/validationStore";

beforeEach(() => {
  useValidationStore.getState().clear();
  useExecutionStore.getState().clear();
  useSuppressionStore.getState().clear();
});

function seedValidityFinding() {
  useValidationStore.getState().setResult({
    diagnostics: [
      {
        severity: "error",
        code: "fit_before_split",
        message: "scale fits a transform upstream of split",
        node_id: "scale",
        rule_id: "fit_before_split",
        related_node_ids: ["split"],
      },
    ],
    edge_compatibility: {},
  });
}

test("suppressing a validity finding removes it from the list immediately", () => {
  seedValidityFinding();
  render(<ProblemsPanel onNavigate={() => {}} />);
  expect(screen.getByTestId("problem-rule-title")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("problem-suppress"));
  expect(screen.queryByTestId("problem-rule-title")).not.toBeInTheDocument();
});

test("cancelling the suppress prompt keeps the finding", () => {
  seedValidityFinding();
  render(<ProblemsPanel onNavigate={() => {}} />);
  expect(screen.getByTestId("problem-rule-title")).toBeInTheDocument();

  const prompt = vi.spyOn(window, "prompt").mockReturnValue(null);
  fireEvent.click(screen.getByTestId("problem-suppress"));
  prompt.mockRestore();

  expect(screen.getByTestId("problem-rule-title")).toBeInTheDocument();
});
