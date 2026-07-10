import type { JSX } from "react";

import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { useUpstreamColumns } from "./useUpstreamColumns";

interface ColumnSelectProps {
  nodeId: string;
  testId: string;
  value: string;
  onChange: (value: string) => void;
}

export function ColumnSelect({
  nodeId,
  testId,
  value,
  onChange,
}: ColumnSelectProps): JSX.Element {
  const columns = useUpstreamColumns(nodeId);

  if (columns.length === 0) {
    return (
      <Input
        type="text"
        data-testid={testId}
        value={value}
        placeholder="Run upstream nodes to populate"
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <Select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" />
      {columns.map((col) => (
        <option key={col} value={col}>
          {col}
        </option>
      ))}
    </Select>
  );
}

interface ColumnMultiSelectProps {
  nodeId: string;
  testId: string;
  value: string[];
  onChange: (value: string[]) => void;
}

export function ColumnMultiSelect({
  nodeId,
  testId,
  value,
  onChange,
}: ColumnMultiSelectProps): JSX.Element {
  const columns = useUpstreamColumns(nodeId);

  if (columns.length === 0) {
    return (
      <Input
        type="text"
        data-testid={testId}
        value={Array.isArray(value) ? value.join(", ") : ""}
        placeholder="Run upstream nodes to populate"
        onChange={(e) => {
          const parsed = e.target.value
            .split(",")
            .map((s) => s.trim())
            .filter((s) => s.length > 0);
          onChange(parsed);
        }}
      />
    );
  }

  const selected = new Set(Array.isArray(value) ? value : []);

  function toggle(col: string) {
    const next = new Set(selected);
    if (next.has(col)) {
      next.delete(col);
    } else {
      next.add(col);
    }
    onChange([...next]);
  }

  return (
    <div data-testid={testId}>
      {columns.map((col) => (
        <label
          key={col}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.35rem",
            padding: "0.15rem 0",
            fontSize: "var(--text-sm)",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={selected.has(col)}
            onChange={() => toggle(col)}
          />
          {col}
        </label>
      ))}
    </div>
  );
}
