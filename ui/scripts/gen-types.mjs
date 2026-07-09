// Generate TypeScript types from the committed JSON Schemas (Epic 5 Story 2 / Epic 14 Story 4;
// ADR 0014 Decision 5). Each schema in src/generated/*.schema.json is Pydantic-emitted output
// (the authoritative contract — do NOT hand-edit it). Pydantic's `Graph` schema is recursive
// (Node.subgraph -> Graph) with a `$defs` section and a root-level `$ref`, which the
// json-schema-to-typescript CLI cannot consume directly; `GraphMutation`/`SessionEvent` are not
// recursive so their root is already concrete, but may still carry a `$defs` section for nested
// types (Node, Edge, ...). `adaptSchema` handles both shapes WITHOUT mutating the committed
// artifacts: it renames `$defs` -> `definitions`, and if the root is a bare `$ref`, promotes the
// `$ref` target to the concrete root schema.
//
// Run via `npm run gen:types`. Every committed src/generated/*.ts must always match this
// script's output for its schema (the Node CI job enforces it with `git diff`).
import { compile } from "json-schema-to-typescript";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const GENERATED_DIR = resolve(here, "../src/generated");

/**
 * Adapt a Pydantic-emitted schema into the `definitions`/concrete-root shape
 * json-schema-to-typescript expects. Returns a new object; the input is not mutated.
 */
function adaptSchema(schema) {
  const rewritten = JSON.parse(
    JSON.stringify(schema).replaceAll("#/$defs/", "#/definitions/"),
  );
  const { $defs, ...rest } = rewritten;
  const definitions = $defs ?? {};
  if (rest.$ref) {
    const rootName = rest.$ref.split("/").pop();
    if (!rootName || !definitions[rootName]) {
      throw new Error(
        `expected a root $ref into $defs; got ${JSON.stringify(rest.$ref)}`,
      );
    }
    return { ...definitions[rootName], title: rootName, definitions };
  }
  return { ...rest, definitions };
}

const TARGETS = [
  { schema: "ir", rootName: "Graph", out: "ir" },
  { schema: "mutation", rootName: "GraphMutation", out: "mutation" },
  { schema: "session_event", rootName: "SessionEvent", out: "session_event" },
];

for (const { schema, rootName, out } of TARGETS) {
  const schemaPath = resolve(GENERATED_DIR, `${schema}.schema.json`);
  const outPath = resolve(GENERATED_DIR, `${out}.ts`);
  const raw = JSON.parse(readFileSync(schemaPath, "utf8"));
  const adapted = adaptSchema(raw);
  const banner = `/* AUTO-GENERATED from ${schema}.schema.json by \`npm run gen:types\`. Do not edit. */`;
  const ts = await compile(adapted, rootName, {
    bannerComment: banner,
    additionalProperties: false,
  });
  writeFileSync(outPath, ts);
  console.log(`wrote ${outPath}`);
}
