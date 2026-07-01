// Renders the per-node config form (Inspector's Config tab). One labeled widget per param,
// driven entirely by catalog param metadata + the pure helpers in `widgets.ts` -- no bespoke
// form per node type. The store param value is the source of truth; this component never keeps
// a local copy.

import type { CatalogParam } from "../catalog/types";
import { useCatalog } from "../catalog/useCatalog";
import { useGraphStore } from "../store/graphStore";
import type { NodeModel, ParamModel } from "../store/model";
import {
  formatValue,
  parseValue,
  validateValue,
  widgetForParam,
} from "./widgets";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

function resolveCatalogParam(
  meta: CatalogParam | undefined,
  param: ParamModel,
): CatalogParam {
  if (meta) {
    return meta;
  }
  // Offline / catalog-drift fallback: still renders a usable widget from the type token alone.
  return { name: param.name, type_token: param.typeToken };
}

interface ParamRowProps {
  node: NodeModel;
  param: ParamModel;
  meta: CatalogParam | undefined;
}

function ParamRow({ node, param, meta }: ParamRowProps): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const catalogParam = resolveCatalogParam(meta, param);
  const kind = widgetForParam(catalogParam);
  const error = validateValue(catalogParam, param.value);
  const testId = `param-${param.name}`;

  let widget: JSX.Element;
  if (kind === "select") {
    const choices = catalogParam.hints?.choices ?? [];
    widget = (
      <Select
        data-testid={testId}
        value={formatValue(catalogParam, param.value)}
        onChange={(e) =>
          setParam(
            node.id,
            param.name,
            parseValue(catalogParam, e.target.value),
          )
        }
      >
        <option value="" />
        {choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </Select>
    );
  } else if (kind === "checkbox") {
    widget = (
      <input
        type="checkbox"
        data-testid={testId}
        checked={Boolean(param.value)}
        onChange={(e) => setParam(node.id, param.name, e.target.checked)}
      />
    );
  } else if (kind === "number") {
    const hints = catalogParam.hints;
    widget = (
      <Input
        type="number"
        data-testid={testId}
        value={formatValue(catalogParam, param.value)}
        min={hints?.min ?? undefined}
        max={hints?.max ?? undefined}
        step={hints?.step ?? undefined}
        onChange={(e) =>
          setParam(
            node.id,
            param.name,
            parseValue(catalogParam, e.target.value),
          )
        }
      />
    );
  } else {
    // text + list both edit as a plain text input; `parseValue` splits a list on commas, and
    // the "comma-separated" hint below is rendered only for the list kind.
    widget = (
      <Input
        type="text"
        data-testid={testId}
        value={formatValue(catalogParam, param.value)}
        onChange={(e) =>
          setParam(
            node.id,
            param.name,
            parseValue(catalogParam, e.target.value),
          )
        }
      />
    );
  }

  return (
    <div style={{ marginBottom: "0.75rem" }}>
      <label
        style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}
      >
        {meta?.label ?? param.name}
        {catalogParam.required ? " *" : ""}
      </label>
      {widget}
      {kind === "list" ? (
        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
          comma-separated
        </div>
      ) : null}
      {meta?.help ? (
        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{meta.help}</div>
      ) : null}
      {error ? (
        <span data-testid={`error-${param.name}`} style={{ color: "var(--danger)" }}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function ConfigForm({ node }: { node: NodeModel }): JSX.Element {
  const catalog = useCatalog();
  const spec = catalog.nodes.find((n) => n.type === node.type);

  if (node.params.length === 0) {
    return (
      <div data-testid="config-form">
        <p data-testid="config-no-params" style={{ color: "var(--text-secondary)" }}>
          This node has no parameters.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="config-form">
      {node.params.map((param) => {
        const meta = spec?.params.find((p) => p.name === param.name);
        return (
          <ParamRow key={param.name} node={node} param={param} meta={meta} />
        );
      })}
    </div>
  );
}
