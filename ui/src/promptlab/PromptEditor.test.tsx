import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { PromptEditor } from "./PromptEditor";

test("renders system/user textareas with their values", () => {
  render(
    <PromptEditor
      system="You are {{persona}}."
      user="{{question}}"
      onSystemChange={vi.fn()}
      onUserChange={vi.fn()}
    />,
  );
  expect(screen.getByTestId("prompt-editor-system")).toHaveValue(
    "You are {{persona}}.",
  );
  expect(screen.getByTestId("prompt-editor-user")).toHaveValue("{{question}}");
});

test("typing in the system field calls onSystemChange", () => {
  const onSystemChange = vi.fn();
  render(
    <PromptEditor
      system=""
      user=""
      onSystemChange={onSystemChange}
      onUserChange={vi.fn()}
    />,
  );
  const systemField = screen.getByTestId("prompt-editor-system");
  fireEvent.change(systemField, { target: { value: "New system prompt" } });
  expect(onSystemChange).toHaveBeenCalledTimes(1);
  expect(onSystemChange).toHaveBeenCalledWith("New system prompt");
});

test("variable table shows the union of both fields' variables", () => {
  render(
    <PromptEditor
      system="{{a}} {{b}}"
      user="{{b}} {{c}}"
      onSystemChange={vi.fn()}
      onUserChange={vi.fn()}
    />,
  );
  const variablesContainer = screen.getByTestId("prompt-editor-variables");
  expect(within(variablesContainer).getByText("a")).toBeInTheDocument();
  expect(within(variablesContainer).getByText("b")).toBeInTheDocument();
  expect(within(variablesContainer).getByText("c")).toBeInTheDocument();
  expect(
    within(variablesContainer).queryByText("No variables detected"),
  ).not.toBeInTheDocument();
});

test("empty templates show the no-variables message", () => {
  render(
    <PromptEditor
      system=""
      user=""
      onSystemChange={vi.fn()}
      onUserChange={vi.fn()}
    />,
  );
  expect(screen.getByText("No variables detected")).toBeInTheDocument();
});

test("highlighted preview renders a mark per variable occurrence", () => {
  const { container } = render(
    <PromptEditor
      system="Hi {{name}}, you are {{name}}."
      user=""
      onSystemChange={vi.fn()}
      onUserChange={vi.fn()}
    />,
  );
  expect(container.querySelectorAll(".ef-promptlab-editor__mark")).toHaveLength(
    2,
  );
});
