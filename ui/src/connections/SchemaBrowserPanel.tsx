import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { useConnectionProfiles } from "../catalog/useConnectionProfiles";
import { Select } from "../ui/Select";

export interface SchemaRow {
  database: string | null;
  schema: string | null;
  table: string;
  column: string | null;
  data_type: string | null;
  nullable: boolean | null;
}

export interface SchemaNode {
  name: string;
  tables: string[];
}

export interface DatabaseNode {
  name: string;
  schemas: SchemaNode[];
}

export function buildRelationTree(rows: SchemaRow[]): DatabaseNode[] {
  const dbMap = new Map<string, Map<string, Set<string>>>();

  for (const row of rows) {
    const db = row.database ?? "(default)";
    const schema = row.schema ?? "(default)";
    if (!dbMap.has(db)) {
      dbMap.set(db, new Map());
    }
    const schemaMap = dbMap.get(db)!;
    if (!schemaMap.has(schema)) {
      schemaMap.set(schema, new Set());
    }
    schemaMap.get(schema)!.add(row.table);
  }

  const databases: DatabaseNode[] = [];
  for (const [dbName, schemaMap] of dbMap) {
    const schemas: SchemaNode[] = [];
    for (const [schemaName, tableSet] of schemaMap) {
      schemas.push({
        name: schemaName,
        tables: [...tableSet].sort(),
      });
    }
    schemas.sort((a, b) => a.name.localeCompare(b.name));
    databases.push({ name: dbName, schemas });
  }
  databases.sort((a, b) => a.name.localeCompare(b.name));
  return databases;
}

type ColumnCacheEntry = SchemaRow[] | "loading" | "error";
type ColumnCache = Record<string, ColumnCacheEntry>;

export function SchemaBrowserPanel(): JSX.Element {
  const profiles = useConnectionProfiles();
  const [selectedConnection, setSelectedConnection] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<SchemaRow[]>([]);
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());
  const [columnCache, setColumnCache] = useState<ColumnCache>({});

  useEffect(() => {
    if (!selectedConnection) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRows([]);
    setExpandedTables(new Set());
    setColumnCache({});

    fetch(`/connections/${encodeURIComponent(selectedConnection)}/schema`)
      .then((res) => res.json() as Promise<{ rows: SchemaRow[] }>)
      .then((data) => {
        if (!cancelled) {
          setRows(data.rows ?? []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load schema");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedConnection]);

  // expandedTables/columnCache are keyed by database::schema::table, not the bare table
  // name -- two different schemas can have a same-named table, and buildRelationTree
  // already nests them under separate DatabaseNode/SchemaNode entries, so the expand/cache
  // state must not collapse them onto one key.
  function toggleTable(key: string, table: string) {
    setExpandedTables((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });

    if (columnCache[key]) return;
    setColumnCache((cache) => ({ ...cache, [key]: "loading" }));
    fetch(
      `/connections/${encodeURIComponent(selectedConnection)}/schema?relation=${encodeURIComponent(table)}`,
    )
      .then(async (res) => {
        const body = await res.json();
        if (!res.ok) {
          setColumnCache((c) => ({ ...c, [key]: "error" }));
          return;
        }
        const cols: SchemaRow[] = body.rows ?? [];
        setColumnCache((c) => ({ ...c, [key]: cols }));
      })
      .catch(() => {
        setColumnCache((c) => ({ ...c, [key]: "error" }));
      });
  }

  const tree = buildRelationTree(rows);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <h2
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: 600,
          margin: 0,
          color: "var(--text-primary)",
        }}
      >
        Browse Schema
      </h2>

      <Select
        data-testid="schema-connection-picker"
        value={selectedConnection}
        onChange={(e) => setSelectedConnection(e.target.value)}
      >
        <option value="">Select a connection…</option>
        {profiles.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}
          </option>
        ))}
      </Select>

      {!selectedConnection && (
        <div
          data-testid="schema-no-connection"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
            lineHeight: 1.5,
          }}
        >
          Select a connection above to browse its schema tree.
        </div>
      )}

      {selectedConnection && loading && (
        <div
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
          }}
        >
          Loading schema…
        </div>
      )}

      {selectedConnection && error && (
        <div
          data-testid="schema-error"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--danger)",
          }}
        >
          {error}
        </div>
      )}

      {selectedConnection && !loading && !error && rows.length === 0 && (
        <div
          data-testid="schema-empty"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
            lineHeight: 1.5,
          }}
        >
          No relations found for this connection.
        </div>
      )}

      {selectedConnection && !loading && !error && rows.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-1)",
            fontSize: "var(--text-sm)",
          }}
        >
          {tree.map((db) => (
            <div key={db.name}>
              <div
                data-testid={`schema-database-${db.name}`}
                style={{
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  padding: "var(--space-1) 0",
                }}
              >
                {db.name}
              </div>
              <div style={{ paddingLeft: "var(--space-3)" }}>
                {db.schemas.map((schema) => (
                  <div key={schema.name}>
                    <div
                      data-testid={`schema-schema-${db.name}-${schema.name}`}
                      style={{
                        fontWeight: 500,
                        color: "var(--text-secondary)",
                        padding: "var(--space-1) 0",
                      }}
                    >
                      {schema.name}
                    </div>
                    <div style={{ paddingLeft: "var(--space-3)" }}>
                      {schema.tables.map((table) => {
                        const key = `${db.name}::${schema.name}::${table}`;
                        return (
                          <div key={table}>
                            <div
                              data-testid={`schema-table-${table}`}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "var(--space-1)",
                                padding: "2px 0",
                                cursor: "pointer",
                                color: "var(--text-primary)",
                              }}
                              onClick={() => toggleTable(key, table)}
                            >
                              {expandedTables.has(key) ? (
                                <ChevronDown size={14} />
                              ) : (
                                <ChevronRight size={14} />
                              )}
                              <span>{table}</span>
                            </div>
                            {expandedTables.has(key) && (
                              <div style={{ paddingLeft: "var(--space-5)" }}>
                                {(() => {
                                  const entry = columnCache[key];
                                  if (!entry) return null;
                                  if (entry === "loading") {
                                    return (
                                      <div
                                        data-testid={`schema-columns-loading-${table}`}
                                        style={{
                                          fontSize: "var(--text-xs)",
                                          color: "var(--text-secondary)",
                                        }}
                                      >
                                        Loading columns…
                                      </div>
                                    );
                                  }
                                  if (entry === "error") {
                                    return (
                                      <div
                                        style={{
                                          fontSize: "var(--text-xs)",
                                          color: "var(--danger)",
                                        }}
                                      >
                                        Failed to load columns
                                      </div>
                                    );
                                  }
                                  return entry.map((col) => (
                                    <div
                                      key={col.column}
                                      data-testid={`schema-column-${table}-${col.column}`}
                                      style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "var(--space-2)",
                                        padding: "1px 0",
                                        fontSize: "var(--text-xs)",
                                      }}
                                    >
                                      <span
                                        style={{ color: "var(--text-primary)" }}
                                      >
                                        {col.column}
                                      </span>
                                      <span
                                        style={{
                                          color: "var(--text-secondary)",
                                        }}
                                      >
                                        {col.data_type}
                                      </span>
                                      <span
                                        style={{
                                          color: "var(--text-secondary)",
                                        }}
                                      >
                                        {col.nullable ? "NULL" : "NOT NULL"}
                                      </span>
                                    </div>
                                  ));
                                })()}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
