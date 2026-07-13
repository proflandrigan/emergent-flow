import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { EditorView } from "@codemirror/view";
import type { Extension } from "@codemirror/state";

import { useDomTheme } from "../theme/useDomTheme";
import { codeEditorExtensions } from "./codeEditorTheme";
import "./CodeEditor.css";

export interface CodeEditorProps {
  value: string;
  language: "python" | "sql";
  onChange: (value: string) => void;
  testId?: string;
  minHeight?: string;
  placeholder?: string;
}

export function CodeEditor({
  value,
  language,
  onChange,
  testId,
  minHeight = "160px",
  placeholder,
}: CodeEditorProps): JSX.Element {
  const theme = useDomTheme();
  const langExtension: Extension = language === "python" ? python() : sql();
  const extensions: Extension[] = [
    langExtension,
    EditorView.lineWrapping,
    ...codeEditorExtensions(theme),
  ];

  const editor = (
    <CodeMirror
      value={value}
      height="auto"
      minHeight={minHeight}
      extensions={extensions}
      onChange={(val) => onChange(val)}
      placeholder={placeholder}
    />
  );

  if (testId) {
    return (
      <div data-testid={testId} className="ef-code-editor">
        {editor}
      </div>
    );
  }

  return <div className="ef-code-editor">{editor}</div>;
}
