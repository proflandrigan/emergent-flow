import { fireEvent, render, screen } from "@testing-library/react";
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

test("sql param renders a textarea, not an input", () => {
  addNode("data.sql_query");
  const el = screen.getByTestId("param-sql");
  expect(el.tagName).toBe("TEXTAREA");
});

test("code param renders a textarea, not an input", () => {
  addNode("script.custom_code");
  const el = screen.getByTestId("param-code");
  expect(el.tagName).toBe("TEXTAREA");
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
