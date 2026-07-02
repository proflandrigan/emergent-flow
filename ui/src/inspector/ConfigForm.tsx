// Renders the per-node config form (Inspector's Config tab). One labeled widget per param,
// driven entirely by catalog param metadata + the pure helpers in `widgets.ts` -- no bespoke
// form per node type. The store param value is the source of truth; this component never keeps
// a local copy.
//
// One exception: nodes that fit/transform/cluster via a curated sklearn estimator (identified
// by having both an `estimator` choice param and a `params` dict param -- Epic 8's fit /
// fit_transform / cluster_detect / cross_validate archetypes) render their `params` dict as one
// widget per curated kwarg (sourced from `catalog.estimators`, keyed on the node's current
// `estimator` value) plus an "Advanced params (JSON)" overflow field for anything not curated,
// instead of a single raw JSON blob -- Epic 8 Story 10's curated/advanced split.

import type { CatalogEstimator, CatalogParam } from "../catalog/types";
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

// Node types whose `params` dict param holds curated sklearn estimator constructor kwargs
// (Epic 8 archetypes). Restricted to an explicit list rather than inferred generically, since
// ml.grid_search's `param_grid` and ml.pipeline's `steps` are dict/list params with a different
// shape (per-param candidate lists / a list of step specs) that a flat curated-kwarg form does
// not fit.
const ESTIMATOR_PARAMS_NODE_TYPES = new Set([
  "ml.fit_estimator",
  "ml.fit_transform",
  "ml.cluster_detect",
  "ml.cross_validate",
]);
const ESTIMATOR_PARAMS_PARAM_NAME = "params";
const ESTIMATOR_CHOICE_PARAM_NAME = "estimator";

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

// Split a curated estimator's kwargs dict into {curated} (keys the catalog knows about for this
// estimator) and {overflow} (anything else -- manually-added advanced kwargs) so each renders in
// its own part of the form without duplicating the other's keys.
function splitCuratedParams(
  value: Record<string, unknown>,
  curatedNames: Set<string>,
): { curated: Record<string, unknown>; overflow: Record<string, unknown> } {
  const curated: Record<string, unknown> = {};
  const overflow: Record<string, unknown> = {};
  for (const [key, v] of Object.entries(value)) {
    if (curatedNames.has(key)) {
      curated[key] = v;
    } else {
      overflow[key] = v;
    }
  }
  return { curated, overflow };
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
  } else if (kind === "json") {
    widget = (
      <textarea
        data-testid={testId}
        value={formatValue(catalogParam, param.value)}
        rows={4}
        style={{
          width: "100%",
          fontFamily: "monospace",
          fontSize: "0.8rem",
          resize: "vertical",
        }}
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

interface EstimatorParamsFieldProps {
  node: NodeModel;
  param: ParamModel;
  meta: CatalogParam | undefined;
  estimator: CatalogEstimator;
}

// Renders `node`'s `params` dict as one widget per curated kwarg for the currently-selected
// estimator, plus an "Advanced params (JSON)" overflow textarea for anything not curated.
// Always writes the FULL merged dict back via setParam so neither side clobbers the other.
// Deliberately stateless (no local React state) -- every widget derives its displayed value
// directly from the store on every render, same invariant as ParamRow above.
function EstimatorParamsField({
  node,
  param,
  meta,
  estimator,
}: EstimatorParamsFieldProps): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const currentValue =
    param.value && typeof param.value === "object" && !Array.isArray(param.value)
      ? (param.value as Record<string, unknown>)
      : {};
  const curatedNames = new Set(estimator.params.map((p) => p.name));
  const { curated, overflow } = splitCuratedParams(currentValue, curatedNames);

  function writeCurated(name: string, value: unknown) {
    setParam(node.id, ESTIMATOR_PARAMS_PARAM_NAME, {
      ...curated,
      [name]: value,
      ...overflow,
    });
  }

  function writeOverflow(raw: string) {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      setParam(node.id, ESTIMATOR_PARAMS_PARAM_NAME, { ...curated, ...parsed });
    } catch {
      // Invalid JSON: don't commit yet. The textarea's value is derived from the store (below),
      // so an invalid in-progress edit simply doesn't take effect until it parses.
    }
  }

  return (
    <div data-testid={`estimator-params-${param.name}`} style={{ marginBottom: "0.75rem" }}>
      <label style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}>
        {meta?.label ?? param.name}
      </label>
      {estimator.params.map((kwarg) => {
        const value = curated[kwarg.name] ?? kwarg.default;
        const testId = `estimator-param-${kwarg.name}`;
        let kwargWidget: JSX.Element;
        if (kwarg.choices && kwarg.choices.length > 0) {
          kwargWidget = (
            <Select
              data-testid={testId}
              value={value === null || value === undefined ? "" : String(value)}
              onChange={(e) => writeCurated(kwarg.name, e.target.value)}
            >
              <option value="" />
              {kwarg.choices.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </Select>
          );
        } else if (kwarg.type === "bool") {
          kwargWidget = (
            <input
              type="checkbox"
              data-testid={testId}
              checked={Boolean(value)}
              onChange={(e) => writeCurated(kwarg.name, e.target.checked)}
            />
          );
        } else if (kwarg.type === "int" || kwarg.type === "float") {
          kwargWidget = (
            <Input
              type="number"
              data-testid={testId}
              step={kwarg.type === "int" ? 1 : undefined}
              value={value === null || value === undefined ? "" : String(value)}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw.trim() === "") {
                  writeCurated(kwarg.name, null);
                  return;
                }
                const n = Number(raw);
                if (Number.isNaN(n)) {
                  writeCurated(kwarg.name, null);
                  return;
                }
                writeCurated(kwarg.name, kwarg.type === "int" ? Math.round(n) : n);
              }}
            />
          );
        } else {
          kwargWidget = (
            <Input
              type="text"
              data-testid={testId}
              value={value === null || value === undefined ? "" : String(value)}
              onChange={(e) => writeCurated(kwarg.name, e.target.value)}
            />
          );
        }
        return (
          <div key={kwarg.name} style={{ marginBottom: "0.5rem" }}>
            <label style={{ display: "block", fontSize: "0.85rem" }}>{kwarg.name}</label>
            {kwargWidget}
            {kwarg.help ? (
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                {kwarg.help}
              </div>
            ) : null}
          </div>
        );
      })}
      <div style={{ marginTop: "0.5rem" }}>
        <label style={{ display: "block", fontSize: "0.85rem" }}>Advanced params (JSON)</label>
        <textarea
          data-testid={`estimator-params-advanced-${param.name}`}
          rows={3}
          style={{
            width: "100%",
            fontFamily: "monospace",
            fontSize: "0.8rem",
            resize: "vertical",
          }}
          value={JSON.stringify(overflow, null, 2)}
          onChange={(e) => writeOverflow(e.target.value)}
        />
      </div>
    </div>
  );
}

// Renders the `estimator` choice param for a curated-estimator node type. Identical to
// ParamRow's "select" branch, except changing the estimator also resets the sibling `params`
// dict to {} -- otherwise a kwarg valid only for the PREVIOUS estimator lingers as unrecognized
// "overflow" in EstimatorParamsField and gets resubmitted verbatim on the next curated edit,
// which the backend rejects with InvalidEstimatorParamsError for the newly-selected estimator.
function EstimatorChoiceRow({ node, param, meta }: ParamRowProps): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const catalogParam = resolveCatalogParam(meta, param);
  const choices = catalogParam.hints?.choices ?? [];
  const error = validateValue(catalogParam, param.value);
  const testId = `param-${param.name}`;

  return (
    <div style={{ marginBottom: "0.75rem" }}>
      <label
        style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}
      >
        {meta?.label ?? param.name}
        {catalogParam.required ? " *" : ""}
      </label>
      <Select
        data-testid={testId}
        value={formatValue(catalogParam, param.value)}
        onChange={(e) => {
          const next = parseValue(catalogParam, e.target.value);
          if (next !== param.value) {
            setParam(node.id, ESTIMATOR_PARAMS_PARAM_NAME, {});
          }
          setParam(node.id, param.name, next);
        }}
      >
        <option value="" />
        {choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </Select>
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

  const estimatorValue = node.params.find(
    (p) => p.name === ESTIMATOR_CHOICE_PARAM_NAME,
  )?.value;
  const catalogEstimator =
    ESTIMATOR_PARAMS_NODE_TYPES.has(node.type) && typeof estimatorValue === "string"
      ? catalog.estimators.find((e) => e.key === estimatorValue)
      : undefined;

  return (
    <div data-testid="config-form">
      {node.params.map((param) => {
        const meta = spec?.params.find((p) => p.name === param.name);
        if (catalogEstimator && param.name === ESTIMATOR_PARAMS_PARAM_NAME) {
          return (
            <EstimatorParamsField
              key={param.name}
              node={node}
              param={param}
              meta={meta}
              estimator={catalogEstimator}
            />
          );
        }
        if (
          ESTIMATOR_PARAMS_NODE_TYPES.has(node.type) &&
          param.name === ESTIMATOR_CHOICE_PARAM_NAME
        ) {
          return (
            <EstimatorChoiceRow key={param.name} node={node} param={param} meta={meta} />
          );
        }
        return <ParamRow key={param.name} node={node} param={param} meta={meta} />;
      })}
    </div>
  );
}
