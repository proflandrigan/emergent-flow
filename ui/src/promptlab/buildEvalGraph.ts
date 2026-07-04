import type { Graph, Node, Param, Port } from "../generated/ir";
import { newId } from "../store/ids";

export interface EvalVariantParams {
  provider: string;
  model: string;
  temperature?: number;
  max_tokens?: number;
  response_format?: "text" | "json";
  response_schema?: Record<string, unknown> | null;
  api_key_env?: string | null;
}

export interface BuildEvalGraphInput {
  system: string;
  user: string;
  variants: EvalVariantParams[];
}

export interface BuildEvalGraphResult {
  graph: Graph;
  nodeId: string;
}

// Builds a minimal single-node IR graph containing one `eval.run` node, for the Prompt Lab's
// "run" action (Epic 9 Story 8). The `dataset` IN port is left unwired -- the caller supplies
// the dataset directly as `inputs.dataset` on a POST /execute_node call (see
// `emergentflow/server/service.py`'s `execute_node`, which runs a single node against
// caller-supplied inputs with no upstream wiring required).
export function buildEvalGraph(
  input: BuildEvalGraphInput,
): BuildEvalGraphResult {
  const nodeId = newId("node");

  const params: Param[] = [
    { name: "system", type_token: "str", value: input.system },
    { name: "user", type_token: "str", value: input.user },
    {
      name: "variants",
      type_token: "list[dict]",
      value: input.variants as unknown as Param["value"],
    },
  ];

  const ports: Port[] = [
    {
      id: newId("port"),
      name: "dataset",
      direction: "in",
      data_type: "DataFrame",
    },
    {
      id: newId("port"),
      name: "results",
      direction: "out",
      data_type: "DataFrame",
    },
  ];

  const node: Node = {
    id: nodeId,
    type: "eval.run",
    label: "Eval Run",
    paradigm: "functional",
    params,
    ports,
  };

  const graph: Graph = {
    paradigm: "functional",
    nodes: { [nodeId]: node },
    edges: {},
  };

  return { graph, nodeId };
}
