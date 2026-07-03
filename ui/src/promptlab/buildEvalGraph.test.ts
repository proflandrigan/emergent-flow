import { describe, expect, test } from "vitest";

import { buildEvalGraph } from "./buildEvalGraph";

describe("buildEvalGraph", () => {
  test("builds a single-node graph", () => {
    const result = buildEvalGraph({
      system: "You are {{persona}}.",
      user: "{{question}}",
      variants: [{ provider: "anthropic", model: "claude-sonnet-5" }],
    });

    const nodes = result.graph.nodes ?? {};
    expect(Object.keys(nodes)).toHaveLength(1);

    const node = nodes[result.nodeId];
    expect(node).toBeDefined();
    expect(node.type).toBe("eval.run");
  });

  test("params carry system/user/variants", () => {
    const variants = [{ provider: "anthropic", model: "claude-sonnet-5" }];
    const result = buildEvalGraph({
      system: "You are {{persona}}.",
      user: "{{question}}",
      variants,
    });

    const node = result.graph.nodes![result.nodeId];
    const params = node.params ?? [];

    const systemParam = params.find((p) => p.name === "system");
    const userParam = params.find((p) => p.name === "user");
    const variantsParam = params.find((p) => p.name === "variants");

    expect(systemParam?.value).toBe("You are {{persona}}.");
    expect(userParam?.value).toBe("{{question}}");
    expect(variantsParam?.value).toEqual(variants);
  });

  test("ports declared correctly", () => {
    const result = buildEvalGraph({
      system: "sys",
      user: "usr",
      variants: [{ provider: "anthropic", model: "claude-sonnet-5" }],
    });

    const node = result.graph.nodes![result.nodeId];
    const ports = node.ports ?? [];

    expect(ports).toHaveLength(2);

    const inPort = ports.find((p) => p.direction === "in");
    const outPort = ports.find((p) => p.direction === "out");

    expect(inPort).toMatchObject({ name: "dataset", data_type: "DataFrame" });
    expect(outPort).toMatchObject({ name: "results", data_type: "DataFrame" });
  });

  test("no edges", () => {
    const result = buildEvalGraph({
      system: "sys",
      user: "usr",
      variants: [{ provider: "anthropic", model: "claude-sonnet-5" }],
    });

    expect(Object.keys(result.graph.edges ?? {})).toHaveLength(0);
  });

  test("unique node ids across calls", () => {
    const input = {
      system: "sys",
      user: "usr",
      variants: [{ provider: "anthropic", model: "claude-sonnet-5" }],
    };

    const first = buildEvalGraph(input);
    const second = buildEvalGraph(input);

    expect(first.nodeId).not.toBe(second.nodeId);
  });
});
