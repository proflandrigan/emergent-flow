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
  paradigm: string;
  ports: CatalogPort[];
  params: CatalogParam[];
}

export interface Catalog {
  catalog_version: number;
  nodes: CatalogNode[];
}
