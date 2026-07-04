import type { JSX } from "react";

import "./PromptEditor.css";
import {
  extractVariablesFromTemplates,
  splitTemplateSegments,
} from "./variables";

export interface PromptEditorProps {
  system: string;
  user: string;
  onSystemChange: (value: string) => void;
  onUserChange: (value: string) => void;
}

function HighlightedPreview({ template }: { template: string }): JSX.Element {
  const segments = splitTemplateSegments(template);
  return (
    <div
      className="ef-promptlab-editor__preview"
      aria-hidden={template.length === 0}
    >
      {segments.map((segment, i) =>
        segment.kind === "var" ? (
          <mark key={i} className="ef-promptlab-editor__mark">
            {`{{${segment.value}}}`}
          </mark>
        ) : (
          <span key={i}>{segment.value}</span>
        ),
      )}
    </div>
  );
}

export function PromptEditor({
  system,
  user,
  onSystemChange,
  onUserChange,
}: PromptEditorProps): JSX.Element {
  const variables = extractVariablesFromTemplates([system, user]);

  return (
    <div className="ef-promptlab-editor">
      <label className="ef-promptlab-editor__field">
        <span>System</span>
        <textarea
          className="ef-promptlab-editor__textarea"
          value={system}
          onChange={(e) => onSystemChange(e.target.value)}
          placeholder="You are a {{persona}} assistant."
          data-testid="prompt-editor-system"
        />
        <HighlightedPreview template={system} />
      </label>

      <label className="ef-promptlab-editor__field">
        <span>User</span>
        <textarea
          className="ef-promptlab-editor__textarea"
          value={user}
          onChange={(e) => onUserChange(e.target.value)}
          placeholder="Answer this: {{question}}"
          data-testid="prompt-editor-user"
        />
        <HighlightedPreview template={user} />
      </label>

      <div
        className="ef-promptlab-editor__variables"
        data-testid="prompt-editor-variables"
      >
        {variables.length === 0 ? (
          <span className="ef-promptlab-editor__no-variables">
            No variables detected
          </span>
        ) : (
          variables.map((name) => (
            <span key={name} className="ef-promptlab-editor__variable-chip">
              {name}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
