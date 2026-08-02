// Lookup helpers over the committed experiment-validity rule pack (ADR 0012). The canvas
// explains a finding's rule from this data, with no Python round-trip.

import validityRulesArtifact from "../generated/validity_rules.json";

export interface ValidityRuleMeta {
  id: string;
  severity: "error" | "warning";
  confidence: string;
  title: string;
  rationale: string;
}

const RULES = (validityRulesArtifact as unknown as {
  pack_version: number;
  rules: ValidityRuleMeta[];
}).rules;

const BY_ID: Map<string, ValidityRuleMeta> = new Map(RULES.map((r) => [r.id, r]));

export function ruleMeta(ruleId: string | null | undefined): ValidityRuleMeta | undefined {
  if (!ruleId) return undefined;
  return BY_ID.get(ruleId);
}

export const rulePackVersion = (
  validityRulesArtifact as unknown as { pack_version: number }
).pack_version;
