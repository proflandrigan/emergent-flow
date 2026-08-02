// "Flow parameters" section (issue #116): the Inspector's Config tab when nothing is selected.
// Defines / edits the graph-level parameters that node params can `ref` (bound via ConfigForm's
// ref affordance). Reads/writes the graph-store `params` map directly.

import { Plus, Trash2 } from "lucide-react";
import { useGraphStore } from "../store/graphStore";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import type { ParamModel } from "../store/model";

const TYPE_OPTIONS = ["str", "int", "float", "bool"];

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function parseValue(typeToken: string, raw: string): unknown {
  if (typeToken === "int") {
    const n = Number(raw);
    return Number.isNaN(n) ? null : Math.round(n);
  }
  if (typeToken === "float") {
    const n = Number(raw);
    return Number.isNaN(n) ? null : n;
  }
  if (typeToken === "bool") {
    return raw === "true";
  }
  return raw;
}

function ParamRow({
  param,
}: {
  param: ParamModel;
}): JSX.Element {
  const setGraphParamValue = useGraphStore((s) => s.setGraphParamValue);
  const setGraphParamType = useGraphStore((s) => s.setGraphParamType);
  const setGraphParamDescription = useGraphStore((s) => s.setGraphParamDescription);
  const removeGraphParam = useGraphStore((s) => s.removeGraphParam);

  const valueWidget =
    param.typeToken === "bool" ? (
      <input
        type="checkbox"
        data-testid={`flow-param-value-${param.name}`}
        checked={Boolean(param.value)}
        onChange={(e) => setGraphParamValue(param.name, e.target.checked)}
      />
    ) : (
      <Input
        type="text"
        data-testid={`flow-param-value-${param.name}`}
        value={formatValue(param.value)}
        onChange={(e) => setGraphParamValue(param.name, parseValue(param.typeToken, e.target.value))}
      />
    );

  return (
    <div data-testid={`flow-param-${param.name}`} style={{ marginBottom: "0.75rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}>
        <span style={{ fontWeight: 600 }}>{param.name}</span>
        <Select
          data-testid={`flow-param-type-${param.name}`}
          value={param.typeToken}
          onChange={(e) => setGraphParamType(param.name, e.target.value)}
        >
          {TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <IconButton
          aria-label={`Remove flow parameter ${param.name}`}
          data-testid={`flow-param-remove-${param.name}`}
          onClick={() => removeGraphParam(param.name)}
        >
          <Trash2 size={14} />
        </IconButton>
      </div>
      <div style={{ marginTop: "0.25rem" }}>{valueWidget}</div>
      <Input
        type="text"
        data-testid={`flow-param-description-${param.name}`}
        placeholder="description"
        value={param.description ?? ""}
        onChange={(e) => setGraphParamDescription(param.name, e.target.value)}
      />
    </div>
  );
}

export function FlowParamsPanel(): JSX.Element {
  const params = useGraphStore((s) => s.params);
  const addGraphParam = useGraphStore((s) => s.addGraphParam);
  const entries = Object.values(params ?? {});

  return (
    <div data-testid="flow-params-panel">
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
        <span style={{ fontWeight: 600 }}>Flow parameters</span>
        <Button
          variant="ghost"
          data-testid="flow-params-add"
          onClick={addGraphParam}
        >
          <Plus size={14} /> Add parameter
        </Button>
      </div>
      {entries.length === 0 ? (
        <p data-testid="flow-params-empty" style={{ color: "var(--text-secondary)" }}>
          No flow parameters yet. Add one to let node params reference a graph-level value.
        </p>
      ) : (
        entries.map((param) => <ParamRow key={param.name} param={param} />)
      )}
    </div>
  );
}
