// Generate TypeScript types from the committed IR JSON Schema (Epic 5 Story 2; ADR 0014
// Decision 5). The schema in src/generated/ir.schema.json is the published Pydantic output
// (the authoritative contract — do NOT hand-edit it). Pydantic emits a recursive schema
// (Node.subgraph -> Graph) with a `$defs` section and a root-level `$ref`, which the
// json-schema-to-typescript CLI cannot consume directly. This script adapts the schema for
// the generator WITHOUT mutating the committed artifact: it renames `$defs` -> `definitions`
// and promotes the root `$ref` target to the concrete root schema, then compiles.
//
// Run via `npm run gen:types`. The committed src/generated/ir.ts must always match this
// script's output for the current schema (the Node CI job enforces it with `git diff`).
import { compile } from "json-schema-to-typescript";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SCHEMA_PATH = resolve(here, "../src/generated/ir.schema.json");
const OUT_PATH = resolve(here, "../src/generated/ir.ts");

const BANNER =
  "/* AUTO-GENERATED from ir.schema.json by `npm run gen:types`. Do not edit. */";

/**
 * Adapt the Pydantic `$defs`/root-`$ref` schema into the `definitions`/concrete-root shape
 * json-schema-to-typescript expects. Returns a new object; the input is not mutated.
 */
function adaptSchema(schema) {
  const rewritten = JSON.parse(
    JSON.stringify(schema).replaceAll("#/$defs/", "#/definitions/"),
  );
  const definitions = rewritten.$defs ?? {};
  const rootName = (rewritten.$ref ?? "").split("/").pop();
  if (!rootName || !definitions[rootName]) {
    throw new Error(
      `expected a root $ref into $defs; got ${JSON.stringify(rewritten.$ref)}`,
    );
  }
  return { ...definitions[rootName], title: rootName, definitions };
}

const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));
const adapted = adaptSchema(schema);
const ts = await compile(adapted, "Graph", {
  bannerComment: BANNER,
  additionalProperties: false,
});
writeFileSync(OUT_PATH, ts);
console.log(`wrote ${OUT_PATH}`);
