// Renders the per-node config form (Inspector's Config tab). One labeled widget per param,
// driven entirely by catalog param metadata + the pure helpers in `widgets.ts` -- no bespoke
// form per node type. The store param value is the source of truth; this component never keeps
// a local copy.
//
// One exception: node types listed in `CURATED_PARAM_NODES` below (Epic 8's fit / fit_transform /
// cluster_detect / cross_validate archetypes, the transform.* feature-transform nodes, and
// recommend.fit) pair a "pick an algorithm/estimator" choice param with a kwargs dict param whose
// shape is described by a catalog entry (`catalog.estimators` or `catalog.recommenders`). Those
// nodes render their dict param as one widget per curated kwarg (keyed on the node's current
// choice-param value) plus an "Advanced params (JSON)" overflow field for anything not curated,
// instead of a single raw JSON blob -- Epic 8 Story 10's curated/advanced split.

import type { CatalogEstimator, CatalogParam, CatalogRecommender } from "../catalog/types";
import { useCatalog } from "../catalog/useCatalog";
import { useConnectionProfiles, useLlmConnectionProfiles } from "../catalog/useConnectionProfiles";
import { useGraphStore } from "../store/graphStore";
import type { NodeModel, ParamModel } from "../store/model";
import {
  formatValue,
  isListType,
  parseValue,
  validateValue,
  widgetForParam,
} from "./widgets";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { CodeEditor } from "./CodeEditor";
import { ColumnSelect, ColumnMultiSelect } from "./ColumnSelect";
import { QueryBuilderPreview } from "./QueryBuilderPreview";
import { JoinKeyField } from "./JoinKeyField";

// Node types whose `params` dict param holds curated constructor kwargs for a choice param
// (Epic 8 archetypes + recommend.fit). Restricted to an explicit config map rather than inferred
// generically, since ml.grid_search's `param_grid` and ml.pipeline's `steps` are dict/list params
// with a different shape (per-param candidate lists / a list of step specs) that a flat
// curated-kwarg form does not fit.
type CuratedSource = "estimators" | "recommenders";
interface CuratedParamConfig {
  choiceParam: string; // the "pick an algorithm/estimator" select param name
  dictParam: string; // the kwargs dict param name
  source: CuratedSource;
}
const CURATED_PARAM_NODES: Record<string, CuratedParamConfig> = {
  "ml.fit_estimator": { choiceParam: "estimator", dictParam: "params", source: "estimators" },
  "ml.fit_transform": { choiceParam: "estimator", dictParam: "params", source: "estimators" },
  "ml.cluster_detect": { choiceParam: "estimator", dictParam: "params", source: "estimators" },
  "ml.outlier_detect": { choiceParam: "estimator", dictParam: "params", source: "estimators" },
  "ml.cross_validate": { choiceParam: "estimator", dictParam: "params", source: "estimators" },
  "transform.scale_features": {
    choiceParam: "estimator",
    dictParam: "params",
    source: "estimators",
  },
  "transform.encode_categorical": {
    choiceParam: "estimator",
    dictParam: "params",
    source: "estimators",
  },
  "transform.discretize": { choiceParam: "estimator", dictParam: "params", source: "estimators" },
  "transform.generate_features": {
    choiceParam: "estimator",
    dictParam: "params",
    source: "estimators",
  },
  "recommend.fit": { choiceParam: "algorithm", dictParam: "params", source: "recommenders" },
};

const JOIN_KEY_NODES: Record<string, { leftPort: string; rightPort: string }> = {
  "clean.merge": { leftPort: "left", rightPort: "right" },
  "clean.semi_join": { leftPort: "frame", rightPort: "keys" },
};
const JOIN_KEY_PARAMS = new Set(["on", "left_on", "right_on"]);

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

// Only rendered for the (typically single) "connection" param on a node, so the /connections
// fetch(es) below run once per form, not once per param row. Both hooks are always called
// (rules-of-hooks forbids calling one conditionally) and the unused one's data is simply
// discarded -- an extra localhost fetch is a trivial cost.
function ConnectionSelect({
  testId,
  value,
  onChange,
  connectionKind,
}: {
  testId: string;
  value: string;
  onChange: (value: string) => void;
  connectionKind: "warehouse" | "llm";
}): JSX.Element {
  const warehouseProfiles = useConnectionProfiles();
  const llmProfiles = useLlmConnectionProfiles();
  const options =
    connectionKind === "llm"
      ? llmProfiles.map((p) => ({ name: p.name, label: `${p.name} (${p.provider})` }))
      : warehouseProfiles.map((p) => ({ name: p.name, label: `${p.name} (${p.dialect})` }));
  return (
    <Select data-testid={testId} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="" />
      {options.map((o) => (
        <option key={o.name} value={o.name}>
          {o.label}
        </option>
      ))}
    </Select>
  );
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
  } else if (kind === "multiselect") {
    // A list-typed param with choices: a native multi-select writing the selection straight
    // back as an array. It deliberately does NOT route through parseValue -- the selected
    // options are already the typed value, and stringifying them just to re-split on "," is
    // both lossy and pointless.
    const choices = catalogParam.hints?.choices ?? [];
    const selected = Array.isArray(param.value) ? param.value.map(String) : [];
    widget = (
      <Select
        multiple
        size={Math.min(Math.max(choices.length, 2), 8)}
        data-testid={testId}
        value={selected}
        onChange={(e) =>
          setParam(
            node.id,
            param.name,
            Array.from(e.target.selectedOptions, (o) => o.value),
          )
        }
      >
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
  } else if (kind === "sql") {
    widget = (
      <CodeEditor
        testId={testId}
        language="sql"
        value={formatValue(catalogParam, param.value)}
        minHeight="160px"
        onChange={(value) =>
          setParam(node.id, param.name, parseValue(catalogParam, value))
        }
      />
    );
  } else if (kind === "code") {
    widget = (
      <CodeEditor
        testId={testId}
        language="python"
        value={formatValue(catalogParam, param.value)}
        minHeight="200px"
        onChange={(value) =>
          setParam(node.id, param.name, parseValue(catalogParam, value))
        }
      />
    );
  } else if (kind === "markdown") {
    widget = (
      <textarea
        data-testid={testId}
        value={formatValue(catalogParam, param.value)}
        rows={6}
        style={{
          width: "100%",
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
  } else if (kind === "filepath") {
    widget = (
      <div style={{ display: "flex", gap: "var(--space-1)" }}>
        <Input
          type="text"
          data-testid={testId}
          value={formatValue(catalogParam, param.value)}
          placeholder="e.g. models/churn_rf_v3.joblib"
          onChange={(e) =>
            setParam(node.id, param.name, parseValue(catalogParam, e.target.value))
          }
          style={{ flex: 1 }}
        />
        <input
          type="file"
          id={`filepicker-${node.id}-${param.name}`}
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              setParam(node.id, param.name, file.name);
            }
          }}
        />
        <button
          type="button"
          data-testid={`${testId}-browse`}
          onClick={() => {
            document.getElementById(`filepicker-${node.id}-${param.name}`)?.click();
          }}
          style={{
            padding: "var(--space-1) var(--space-2)",
            fontSize: "var(--text-sm)",
            cursor: "pointer",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border-color)",
            background: "var(--bg-secondary)",
          }}
        >
          Browse
        </button>
      </div>
    );
  } else if (kind === "connection") {
    widget = (
      <ConnectionSelect
        testId={testId}
        value={formatValue(catalogParam, param.value)}
        onChange={(value) => setParam(node.id, param.name, parseValue(catalogParam, value))}
        connectionKind={catalogParam.hints?.connection_kind === "llm" ? "llm" : "warehouse"}
      />
    );
  } else if (kind === "column") {
    if (isListType(catalogParam.type_token)) {
      const arrValue = Array.isArray(param.value) ? (param.value as string[]) : [];
      widget = (
        <ColumnMultiSelect
          nodeId={node.id}
          testId={testId}
          value={arrValue}
          onChange={(cols) => setParam(node.id, param.name, cols)}
        />
      );
    } else {
      widget = (
        <ColumnSelect
          nodeId={node.id}
          testId={testId}
          value={formatValue(catalogParam, param.value)}
          onChange={(val) =>
            setParam(node.id, param.name, val)
          }
        />
      );
    }
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
  estimator: CatalogEstimator | CatalogRecommender;
  dictParam: string;
}

// Renders `node`'s dict param as one widget per curated kwarg for the currently-selected
// estimator/algorithm, plus an "Advanced params (JSON)" overflow textarea for anything not
// curated. Always writes the FULL merged dict back via setParam so neither side clobbers the
// other. Deliberately stateless (no local React state) -- every widget derives its displayed
// value directly from the store on every render, same invariant as ParamRow above.
function EstimatorParamsField({
  node,
  param,
  meta,
  estimator,
  dictParam,
}: EstimatorParamsFieldProps): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const currentValue =
    param.value && typeof param.value === "object" && !Array.isArray(param.value)
      ? (param.value as Record<string, unknown>)
      : {};
  const curatedNames = new Set(estimator.params.map((p) => p.name));
  const { curated, overflow } = splitCuratedParams(currentValue, curatedNames);

  function writeCurated(name: string, value: unknown) {
    setParam(node.id, dictParam, {
      ...curated,
      [name]: value,
      ...overflow,
    });
  }

  function writeOverflow(raw: string) {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      setParam(node.id, dictParam, { ...curated, ...parsed });
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
        } else if (kwarg.type === "list") {
          // Comma-separated text, same convention as the top-level "list" widget
          // (widgets.ts's isListType/parseValue/formatValue) -- without this branch a list
          // default like [32, 16, 8] falls into the plain-text branch below, which stringifies
          // the array for display and then writes the raw unparsed string back on every edit
          // instead of an array, corrupting params like mlp_layers/feature_cols/ngram_range.
          const arr = Array.isArray(value) ? value : [];
          // CatalogRecommenderParam has no item-type token (unlike ParamSpec's "list[int]"/
          // "list[float]"), so infer numeric-ness from whichever of the current value or the
          // kwarg's own default is non-empty -- catches mlp_layers/*_tower_layers/ngram_range
          // (numeric defaults) while leaving string lists like feature_cols alone. Without this,
          // every edit writes string items (e.g. "32" instead of 32), which crashes numeric
          // consumers like torch layer sizes or TfidfVectorizer's ngram_range tuple.
          const defaultArr = Array.isArray(kwarg.default) ? kwarg.default : [];
          const sampleArr = arr.length > 0 ? arr : defaultArr;
          const isNumericList = sampleArr.length > 0 && sampleArr.every((v) => typeof v === "number");
          kwargWidget = (
            <Input
              type="text"
              data-testid={testId}
              value={arr.join(", ")}
              onChange={(e) => {
                const parsed = e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter((s) => s.length > 0)
                  .map((s) => {
                    if (!isNumericList) {
                      return s;
                    }
                    const n = Number(s);
                    return Number.isNaN(n) ? s : n;
                  });
                writeCurated(kwarg.name, parsed);
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
        // Only CatalogRecommenderParam carries `required` (sklearn's CatalogEstimatorParam has
        // no such concept -- every constructor kwarg has a default); guard with `in` so this
        // stays a no-op for the estimator-sourced kwargs of the pre-existing curated nodes.
        const kwargRequired = "required" in kwarg && kwarg.required;
        return (
          <div key={kwarg.name} style={{ marginBottom: "0.5rem" }}>
            <label style={{ display: "block", fontSize: "0.85rem" }}>
              {kwarg.name}
              {kwargRequired ? " *" : ""}
            </label>
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

interface EstimatorChoiceRowProps extends ParamRowProps {
  dictParam: string;
}

// Renders the "pick an algorithm/estimator" choice param for a curated-param node type.
// Identical to ParamRow's "select" branch, except changing the choice also resets the sibling
// dict param to {} -- otherwise a kwarg valid only for the PREVIOUS choice lingers as
// unrecognized "overflow" in EstimatorParamsField and gets resubmitted verbatim on the next
// curated edit, which the backend rejects with InvalidEstimatorParamsError for the
// newly-selected choice.
function EstimatorChoiceRow({
  node,
  param,
  meta,
  dictParam,
}: EstimatorChoiceRowProps): JSX.Element {
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
            setParam(node.id, dictParam, {});
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

  const curated = CURATED_PARAM_NODES[node.type];
  const choiceValue = curated
    ? node.params.find((p) => p.name === curated.choiceParam)?.value
    : undefined;
  const curatedEntries = curated
    ? curated.source === "recommenders"
      ? catalog.recommenders
      : catalog.estimators
    : undefined;
  const curatedEntry =
    curatedEntries && typeof choiceValue === "string"
      ? curatedEntries.find((e) => e.key === choiceValue)
      : undefined;

  return (
    <div data-testid="config-form">
      {node.params.map((param) => {
        const meta = spec?.params.find((p) => p.name === param.name);
        const joinKeyPorts = JOIN_KEY_NODES[node.type];
        if (joinKeyPorts && JOIN_KEY_PARAMS.has(param.name)) {
          return (
            <JoinKeyField
              key={param.name}
              node={node}
              param={param}
              meta={meta}
              leftPort={joinKeyPorts.leftPort}
              rightPort={joinKeyPorts.rightPort}
            />
          );
        }
        if (curated && curatedEntry && param.name === curated.dictParam) {
          return (
            <EstimatorParamsField
              key={param.name}
              node={node}
              param={param}
              meta={meta}
              estimator={curatedEntry}
              dictParam={curated.dictParam}
            />
          );
        }
        if (curated && param.name === curated.choiceParam) {
          return (
            <EstimatorChoiceRow
              key={param.name}
              node={node}
              param={param}
              meta={meta}
              dictParam={curated.dictParam}
            />
          );
        }
        return <ParamRow key={param.name} node={node} param={param} meta={meta} />;
      })}
      {node.type === "data.query_builder" ? <QueryBuilderPreview node={node} /> : null}
    </div>
  );
}
