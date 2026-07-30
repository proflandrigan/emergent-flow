// Hand-written TS mirrors of the node catalog shape served by the local
// `emergentflow serve` server (ADR 0013) at `/catalog` and emitted to
// `ui/src/generated/catalog.json`. Kept exact so the palette task can rely on them.

export type CatalogDirection = "in" | "out";
export type CatalogCardinality = "one" | "many";

export interface CatalogValidationHints {
  min?: number | null;
  max?: number | null;
  step?: number | null;
  choices?: string[] | null;
  min_length?: number | null;
  max_length?: number | null;
  pattern?: string | null;
  widget?: string | null;
  connection_kind?: string | null;
}

export interface CatalogParam {
  name: string;
  type_token: string;
  default?: unknown;
  required?: boolean;
  label?: string | null;
  help?: string | null;
  hints?: CatalogValidationHints | null;
}

export interface CatalogPort {
  name: string;
  direction: CatalogDirection;
  data_type?: string;
  cardinality?: CatalogCardinality;
  required?: boolean;
  label?: string | null;
  help?: string | null;
}

export interface CatalogNode {
  type: string;
  version: number;
  family: string;
  label: string;
  category?: string;
  description?: string;
  keywords?: string[];
  paradigm: string;
  ports: CatalogPort[];
  params: CatalogParam[];
  advisor_persona?: string | null;
}

export interface CatalogEstimatorParam {
  name: string;
  type: "bool" | "int" | "float" | "str" | "any";
  default?: unknown;
  help?: string;
  choices?: string[] | null;
}

export interface CatalogEstimator {
  key: string;
  node_type: string;
  archetype: string;
  task: string;
  label: string;
  category: string;
  description: string;
  import_path: string;
  params: CatalogEstimatorParam[];
}

export interface CatalogChart {
  key: string;
  node_type: string;
  label: string;
  category: string;
  description: string;
  px_function: string;
  encodings: string[];
  options: string[];
}

export interface CatalogRecommenderParam {
  name: string;
  type: "bool" | "int" | "float" | "str" | "list" | "any";
  default?: unknown;
  help?: string;
  choices?: string[] | null;
  required?: boolean;
}

export interface CatalogRecommender {
  key: string;
  node_type: string;
  family: string;
  label: string;
  category: string;
  description: string;
  requires_extra?: string | null;
  params: CatalogRecommenderParam[];
}

export interface Catalog {
  catalog_version: number;
  nodes: CatalogNode[];
  estimators: CatalogEstimator[];
  charts: CatalogChart[];
  recommenders: CatalogRecommender[];
}
