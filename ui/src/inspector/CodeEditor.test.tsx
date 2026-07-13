import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { EditorView } from "@codemirror/view";

import { CodeEditor } from "./CodeEditor";

test("renders with a given testId", () => {
  render(
    <CodeEditor value="" language="python" onChange={() => {}} testId="my-editor" />,
  );
  expect(screen.getByTestId("my-editor")).toBeInTheDocument();
});

test("renders the initial value text in the DOM", () => {
  render(
    <CodeEditor
      value="SELECT * FROM table"
      language="sql"
      onChange={() => {}}
      testId="sql-editor"
    />,
  );
  const container = screen.getByTestId("sql-editor");
  expect(container.textContent).toContain("SELECT * FROM table");
});

test("renders line numbers and python syntax highlighting", () => {
  render(
    <CodeEditor value="def f():\n    pass" language="python" onChange={() => {}} testId="py" />,
  );
  const container = screen.getByTestId("py");
  expect(container.querySelector(".cm-gutters")).not.toBeNull();
  expect(container.querySelector(".cm-lineNumbers")).not.toBeNull();
  // Highlighted tokens render as <span> children inside .cm-line (e.g. keywords); a plain,
  // unhighlighted document would just be a bare text node with no spans.
  expect(container.querySelectorAll(".cm-line span").length).toBeGreaterThan(0);
});

test("editing the real CodeMirror document triggers onChange with the updated value", () => {
  const onChange = vi.fn();
  render(
    <CodeEditor value="hello" language="python" onChange={onChange} testId="editor" />,
  );
  const container = screen.getByTestId("editor");
  const editorDom = container.querySelector(".cm-editor") as HTMLElement;
  const view = EditorView.findFromDOM(editorDom);
  expect(view).not.toBeNull();

  view!.dispatch({ changes: { from: view!.state.doc.length, insert: "!" } });

  expect(onChange).toHaveBeenCalledWith("hello!");
});
