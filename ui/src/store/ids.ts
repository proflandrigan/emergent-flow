// Mint a stable, opaque unique id for a node/port/edge. The IR treats ids as opaque strings
// (Python mints them via new_id()); the canvas only needs uniqueness + stability for edge refs.
export function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
