import { fireEvent, render, screen } from "@testing-library/react";
import { EditorView } from "@codemirror/view";
import { beforeEach, expect, test } from "vitest";

import catalogJson from "../generated/catalog.json";
import type { Catalog, CatalogNode } from "../catalog/types";
import { useGraphStore } from "../store/graphStore";
import { ConfigForm } from "./ConfigForm";

// ConfigForm resolves param metadata (choices, required, help) from the live catalog via
// useCatalog(), NOT from the stored node (addNodeFromSpec keeps only param values). In jsdom
// fetch is unmocked, so useCatalog falls back synchronously to this committed catalog -- so the
// tests must use REAL catalog node types for the metadata join to resolve.
const catalog = catalogJson as unknown as Catalog;

function spec(type: string): CatalogNode {
  const found = catalog.nodes.find((n) => n.type === type);
  if (!found) {
    throw new Error(`catalog node not found: ${type}`);
  }
  return found;
}

function addNode(type: string): string {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec(type), { x: 0, y: 0 });
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);
  return id;
}

beforeEach(() => {
  useGraphStore.getState().reset();
});

test("renders a select widget with its choices", () => {
  addNode("clean.impute_missing");
  const select = screen.getByTestId("param-strategy") as HTMLSelectElement;
  const options = Array.from(select.querySelectorAll("option")).map(
    (o) => o.value,
  );
  expect(options).toEqual(["", "mean", "median", "most_frequent"]);
  expect(select.value).toBe("mean");
});

test("typing in a number input updates the store", () => {
  const id = addNode("ml.train_classifier");
  const input = screen.getByTestId("param-random_state") as HTMLInputElement;

  fireEvent.change(input, { target: { value: "5" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "random_state");
  expect(param?.value).toBe(5);
});

test("typing in a text input updates the store", () => {
  const id = addNode("data.load_csv");
  const input = screen.getByTestId("param-encoding");

  fireEvent.change(input, { target: { value: "latin-1" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "encoding");
  expect(param?.value).toBe("latin-1");
});

test("typing in a filepath input updates the store", () => {
  const id = addNode("ml.load_model");
  const input = screen.getByTestId("param-path") as HTMLInputElement;

  fireEvent.change(input, { target: { value: "models/churn.joblib" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "path");
  expect(param?.value).toBe("models/churn.joblib");
});

test("a required-but-empty param shows its error message", () => {
  // data.load_csv's `path` is required with a null default -> empty -> "Required".
  addNode("data.load_csv");
  expect(screen.getByTestId("error-path")).toHaveTextContent("Required");
});

test("renders the no-params message when the node has no params", () => {
  addNode("nn.module");
  expect(screen.getByTestId("config-no-params")).toBeInTheDocument();
});

test("renders curated per-kwarg widgets once a recognized estimator is selected", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.fit_estimator"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "estimator", "RandomForestClassifier");
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const estimator = catalog.estimators.find((e) => e.key === "RandomForestClassifier");
  expect(estimator).toBeDefined();
  for (const kwarg of estimator!.params) {
    expect(screen.getByTestId(`estimator-param-${kwarg.name}`)).toBeInTheDocument();
  }
});

test("editing a curated kwarg field updates only that key in the params dict", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.fit_estimator"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "estimator", "RandomForestClassifier");
  useGraphStore.getState().setParam(id, "params", { n_estimators: 100 });
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const input = screen.getByTestId("estimator-param-n_estimators") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "250" } });

  const updated = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "params");
  expect((updated?.value as Record<string, unknown>).n_estimators).toBe(250);
});

test("editing the advanced params JSON textarea merges into the dict without clobbering curated values", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.fit_estimator"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "estimator", "RandomForestClassifier");
  useGraphStore.getState().setParam(id, "params", { n_estimators: 100 });
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const textarea = screen.getByTestId("estimator-params-advanced-params");
  fireEvent.change(textarea, { target: { value: '{"class_weight": "balanced"}' } });

  const updated = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "params");
  const value = updated?.value as Record<string, unknown>;
  expect(value.class_weight).toBe("balanced");
  expect(value.n_estimators).toBe(100);
});

test("a node type outside the curated-estimator list still uses the plain JSON widget for its dict param", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.grid_search"), { x: 0, y: 0 });
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  expect(screen.getByTestId("param-param_grid")).toBeInTheDocument();
  expect(screen.queryByTestId(/estimator-param-/)).not.toBeInTheDocument();
});

test("ml.pipeline's list-of-dict steps param renders readable JSON, not [object Object]", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.pipeline"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "steps", [
    { estimator: "StandardScaler", params: {} },
    { estimator: "GradientBoostingClassifier", params: { n_estimators: 50 } },
  ]);
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const textarea = screen.getByTestId("param-steps") as HTMLTextAreaElement;
  expect(textarea.value).not.toContain("[object Object]");
  expect(textarea.value).toContain("StandardScaler");
  expect(textarea.value).toContain("GradientBoostingClassifier");
});

test("a curated kwarg with catalog choices renders a select, not a free-text input", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.fit_transform"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "estimator", "SelectKBest");
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const select = screen.getByTestId("estimator-param-score_func") as HTMLSelectElement;
  expect(select.tagName).toBe("SELECT");
  const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
  expect(options).toEqual([
    "",
    "f_classif",
    "f_regression",
    "mutual_info_classif",
    "mutual_info_regression",
  ]);

  fireEvent.change(select, { target: { value: "f_regression" } });
  const updated = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "params");
  expect((updated?.value as Record<string, unknown>).score_func).toBe("f_regression");
});

test("switching estimator clears kwargs that don't belong to the newly selected estimator", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("ml.fit_estimator"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "estimator", "RandomForestClassifier");
  useGraphStore.getState().setParam(id, "params", { n_estimators: 100 });
  let node = useGraphStore.getState().nodes[id];
  const { rerender } = render(<ConfigForm node={node} />);

  const select = screen.getByTestId("param-estimator") as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "LogisticRegression" } });

  const updatedParams = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "params");
  expect(updatedParams?.value).toEqual({});

  // Re-render with the fresh node and confirm the stale kwarg isn't resurrected as "overflow"
  // and resubmitted on the next curated edit (which would previously crash with
  // InvalidEstimatorParamsError on the backend for the newly-selected estimator).
  node = useGraphStore.getState().nodes[id];
  rerender(<ConfigForm node={node} />);
  const advanced = screen.getByTestId(
    "estimator-params-advanced-params",
  ) as HTMLTextAreaElement;
  expect(JSON.parse(advanced.value)).toEqual({});
});

test("sql param renders a CodeMirror editor, not a plain textarea", () => {
  addNode("data.sql_query");
  const el = screen.getByTestId("param-sql");
  expect(el.tagName).toBe("DIV");
  expect(el.querySelector(".cm-editor")).not.toBeNull();
  expect(el.querySelector("textarea")).toBeNull();
});

test("code param renders a CodeMirror editor, not a plain textarea", () => {
  addNode("script.custom_code");
  const el = screen.getByTestId("param-code");
  expect(el.tagName).toBe("DIV");
  expect(el.querySelector(".cm-editor")).not.toBeNull();
  expect(el.querySelector("textarea")).toBeNull();
});

test("editing the sql CodeMirror editor updates the store", () => {
  const id = addNode("data.sql_query");
  const container = screen.getByTestId("param-sql");
  const editorDom = container.querySelector(".cm-editor") as HTMLElement;
  const view = EditorView.findFromDOM(editorDom);
  expect(view).not.toBeNull();

  view!.dispatch({ changes: { from: view!.state.doc.length, insert: "\nSELECT * FROM foo" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "sql");
  expect(param?.value).toContain("SELECT * FROM foo");
});

test("connection param renders a select, not a text input", () => {
  addNode("data.sql_query");
  const el = screen.getByTestId("param-connection");
  expect(el.tagName).toBe("SELECT");
});

test("llm_connection param renders a select, not a text input", () => {
  addNode("llm.call");
  const el = screen.getByTestId("param-llm_connection");
  expect(el.tagName).toBe("SELECT");
});

test("recommend.fit renders curated per-param widgets from catalog.recommenders once an algorithm is selected", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("recommend.fit"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "algorithm", "popularity");
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  // The algorithm choice param resolves via catalog.recommenders (source "recommenders"),
  // not catalog.estimators.
  const recommender = catalog.recommenders.find((r) => r.key === "popularity");
  expect(recommender).toBeDefined();
  for (const kwarg of recommender!.params) {
    expect(screen.getByTestId(`estimator-param-${kwarg.name}`)).toBeInTheDocument();
  }

  // score_type carries curated choices -> renders a select, not a raw JSON blob.
  const scoreType = screen.getByTestId("estimator-param-score_type") as HTMLSelectElement;
  expect(scoreType.tagName).toBe("SELECT");
  const options = Array.from(scoreType.querySelectorAll("option")).map((o) => o.value);
  expect(options).toEqual(["", "count", "mean_rating", "weighted"]);

  // The advanced-JSON overflow field is present (dict param is still named "params").
  expect(screen.getByTestId("estimator-params-advanced-params")).toBeInTheDocument();
});

test("editing a curated recommender kwarg writes into the recommend.fit params dict", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("recommend.fit"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "algorithm", "popularity");
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const scoreType = screen.getByTestId("estimator-param-score_type") as HTMLSelectElement;
  fireEvent.change(scoreType, { target: { value: "weighted" } });

  const updated = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "params");
  expect((updated?.value as Record<string, unknown>).score_type).toBe("weighted");
});

test("editing a list-typed curated recommender kwarg writes an array, not a raw string", () => {
  // Regression guard: a `type: "list"` curated param (e.g. two_tower.user_tower_layers) must
  // round-trip as an array. Without the dedicated "list" widget branch the plain-text fallback
  // would write the unparsed string back, corrupting the params dict for the fitter.
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("recommend.fit"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "algorithm", "two_tower");
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const listField = catalog.recommenders
    .find((r) => r.key === "two_tower")!
    .params.find((p) => p.type === "list");
  expect(listField).toBeDefined();

  const input = screen.getByTestId(`estimator-param-${listField!.name}`) as HTMLInputElement;
  fireEvent.change(input, { target: { value: "64, 32" } });

  const updated = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "params");
  expect((updated?.value as Record<string, unknown>)[listField!.name]).toEqual([64, 32]);
});

test("transform.scale_features renders curated estimator widgets (feature-transform node wired into the curated path)", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("transform.scale_features"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "estimator", "StandardScaler");
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  const estimator = catalog.estimators.find((e) => e.key === "StandardScaler");
  expect(estimator).toBeDefined();
  for (const kwarg of estimator!.params) {
    expect(screen.getByTestId(`estimator-param-${kwarg.name}`)).toBeInTheDocument();
  }
  // No raw JSON blob for the dict param -- it's the curated field instead.
  expect(screen.getByTestId("estimator-params-advanced-params")).toBeInTheDocument();
});

test("a list-typed param with choices renders a multi-select storing an array", () => {
  // ml.compare_models.estimators is list[str] over the estimator catalog. It previously
  // rendered as a single-value <select>, so only one estimator could ever be chosen and the
  // stored value was a bare string -- which the backend iterates character-by-character.
  const id = addNode("ml.compare_models");
  const select = screen.getByTestId("param-estimators") as HTMLSelectElement;

  expect(select.multiple).toBe(true);

  const options = Array.from(select.querySelectorAll("option")).map(
    (o) => o.value,
  );
  expect(options).toContain("RandomForestClassifier");
  expect(options).toContain("Ridge");
  // No blank sentinel option: an empty selection is expressed by selecting nothing.
  expect(options).not.toContain("");

  for (const option of Array.from(select.querySelectorAll("option"))) {
    if (option.value === "RandomForestClassifier" || option.value === "Ridge") {
      option.selected = true;
    }
  }
  fireEvent.change(select);

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "estimators");
  expect(param?.value).toEqual(["RandomForestClassifier", "Ridge"]);
});

test("with a flow param present, a ref_supported param row shows the bind dropdown and binding hides the literal widget", () => {
  useGraphStore.getState().addGraphParam(); // creates param1
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("data.load_csv"), { x: 0, y: 0 });
  const { rerender } = render(
    <ConfigForm node={useGraphStore.getState().nodes[id]} />,
  );

  expect(screen.getByTestId("param-path-ref")).toBeInTheDocument();
  expect(screen.getByTestId("param-encoding-ref")).toBeInTheDocument();

  const refSelect = screen.getByTestId("param-path-ref") as HTMLSelectElement;
  fireEvent.change(refSelect, { target: { value: "param1" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "path");
  expect(param?.ref).toBe("param1");

  // ConfigForm is a controlled component fed a node prop by its parent (the Inspector reads a
  // fresh node from the store each render), so re-render with the updated node.
  rerender(<ConfigForm node={useGraphStore.getState().nodes[id]} />);
  expect(screen.getByTestId("param-path-bound")).toBeInTheDocument();
  expect(screen.queryByTestId("param-path")).toBeNull();
});

test("unbinding a ref (selecting '(literal value)' again) clears ref and shows the literal widget again", () => {
  useGraphStore.getState().addGraphParam(); // creates param1
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("data.load_csv"), { x: 0, y: 0 });
  const { rerender } = render(
    <ConfigForm node={useGraphStore.getState().nodes[id]} />,
  );

  const refSelect = screen.getByTestId("param-path-ref") as HTMLSelectElement;
  fireEvent.change(refSelect, { target: { value: "param1" } });

  fireEvent.change(refSelect, { target: { value: "" } });

  const param = useGraphStore
    .getState()
    .nodes[id].params.find((p) => p.name === "path");
  expect(param?.ref).toBeUndefined();

  rerender(<ConfigForm node={useGraphStore.getState().nodes[id]} />);
  expect(screen.queryByTestId("param-path-bound")).toBeNull();
  expect(screen.getByTestId("param-path")).toBeInTheDocument();
});
