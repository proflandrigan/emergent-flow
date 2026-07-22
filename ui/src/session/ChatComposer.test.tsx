import { expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState, type JSX } from "react";

import { ChatComposer, type ChatComposerProps } from "./ChatComposer";

const PERSONAS = [
  { slug: "data_modeller", label: "Data Modeller", description: "Models data", node_families: [] },
  { slug: "data_scientist", label: "Data Scientist", description: "Does data science", node_families: [] },
  { slug: "researcher", label: "Researcher", description: "Researches things", node_families: [] },
  { slug: "ml_engineer", label: "ML Engineer", description: "Builds models", node_families: [] },
];

function renderComposer(overrides: Partial<ChatComposerProps> = {}) {
  const onSubmit = vi.fn();
  const onChange = vi.fn();

  function Wrapper(): JSX.Element {
    const [value, setValue] = useState("");
    return (
      <ChatComposer
        value={value}
        onChange={(v) => {
          setValue(v);
          onChange(v);
        }}
        onSubmit={onSubmit}
        personas={PERSONAS}
        placeholder="Send a message"
        rows={2}
        data-testid="composer"
        {...overrides}
      />
    );
  }

  return { renderResult: render(<Wrapper />), onSubmit, onChange };
}

function typeIn(text: string): void {
  const input = screen.getByTestId("composer");
  fireEvent.change(input, { target: { value: text } });
}

function pressKey(key: string, shiftKey = false): void {
  const input = screen.getByTestId("composer");
  fireEvent.keyDown(input, { key, shiftKey });
}

test("Pressing Enter (no shift) calls onSubmit and does not add a newline", () => {
  const { onSubmit, onChange } = renderComposer();
  typeIn("hello");
  pressKey("Enter");
  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenLastCalledWith("hello");
});

test("Pressing Shift+Enter does NOT call onSubmit", () => {
  const { onSubmit } = renderComposer();
  typeIn("hello");
  pressKey("Enter", true);
  expect(onSubmit).not.toHaveBeenCalled();
});

test("Typing / opens the palette showing 3 options, not data_modeller", () => {
  renderComposer();
  typeIn("/");
  expect(screen.getByTestId("composer-palette")).toBeInTheDocument();
  expect(
    screen.getByTestId("composer-palette-option-data_scientist"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("composer-palette-option-researcher"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("composer-palette-option-ml_engineer"),
  ).toBeInTheDocument();
  expect(
    screen.queryByTestId("composer-palette-option-data_modeller"),
  ).toBeNull();
});

test("Typing /data-sci narrows the palette to only data_scientist", () => {
  renderComposer();
  typeIn("/data-sci");
  expect(screen.getByTestId("composer-palette")).toBeInTheDocument();
  expect(
    screen.getByTestId("composer-palette-option-data_scientist"),
  ).toBeInTheDocument();
  expect(
    screen.queryByTestId("composer-palette-option-researcher"),
  ).toBeNull();
  expect(
    screen.queryByTestId("composer-palette-option-ml_engineer"),
  ).toBeNull();
});

test("Typing /xyz (matching no command) renders no palette", () => {
  renderComposer();
  typeIn("/xyz");
  expect(screen.queryByTestId("composer-palette")).toBeNull();
});

test("Pressing Enter while palette is open selects first option (data_scientist)", () => {
  const { onChange } = renderComposer();
  typeIn("/");
  pressKey("Enter");
  expect(onChange).toHaveBeenLastCalledWith("/data-scientist ");
});

test("ArrowDown then Enter selects the second option (researcher)", () => {
  const { onChange } = renderComposer();
  typeIn("/");
  pressKey("ArrowDown");
  pressKey("Enter");
  expect(onChange).toHaveBeenLastCalledWith("/researcher ");
});

test("Clicking a palette option selects it and closes palette", () => {
  const { onChange } = renderComposer();
  typeIn("/");
  fireEvent.click(
    screen.getByTestId("composer-palette-option-ml_engineer"),
  );
  expect(onChange).toHaveBeenLastCalledWith("/ml-engineer ");
  expect(screen.queryByTestId("composer-palette")).toBeNull();
});

test("Pressing Escape while palette is open closes it without changing value", () => {
  const { onChange } = renderComposer();
  typeIn("/");
  expect(screen.getByTestId("composer-palette")).toBeInTheDocument();
  pressKey("Escape");
  expect(screen.queryByTestId("composer-palette")).toBeNull();
  expect(onChange).toHaveBeenLastCalledWith("/");
});

test("Typing a space after /foo does not show the palette", () => {
  renderComposer();
  typeIn("/foo ");
  expect(screen.queryByTestId("composer-palette")).toBeNull();
});
