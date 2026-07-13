/* AUTO-GENERATED from ir.schema.json by `npm run gen:types`. Do not edit. */

/**
 * Stable unique identifier for this edge.
 */
export type Id = string;
/**
 * ID of the node containing the port.
 */
export type NodeId = string;
/**
 * ID of the port on the node.
 */
export type PortId = string;
/**
 * Type-compatibility metadata. None="not yet checked". Set to bool by ef.apply_type_compatibility from a ef.validate result.
 */
export type TypeCompatible = boolean | null;
export type Name = string | null;
export type GroupId = string | null;
export type Id1 = string;
export type Label = string | null;
/**
 * First-class execution paradigms (ADR 0003).
 */
export type Paradigm = "functional" | "declarative";
/**
 * Fixed discriminator tag; always "artifact_ref".
 */
export type Kind = "artifact_ref";
/**
 * Optional MIME hint, e.g. "application/parquet".
 */
export type MediaType = string | null;
/**
 * Location of the artifact (path or object-store URI).
 */
export type Uri = string;
export type ParamValue =
  | (string | number | boolean | null)
  | ArtifactRef
  | ParamValue[]
  | {
      [k: string]: ParamValue;
    };
export type Name1 = string;
export type TypeToken = string;
export type Params = Param[];
/**
 * How many connections a port / edge end accepts.
 */
export type Cardinality = "one" | "many";
export type DataType = string;
/**
 * Edge / port directionality.
 */
export type Direction = "in" | "out";
export type Id2 = string;
export type Label1 = string | null;
export type Name2 = string;
export type Ports = Port[];
export type X = number;
export type Y = number;
/**
 * First-class execution paradigms (ADR 0003).
 */
export type Paradigm1 = "functional" | "declarative";
export type SchemaVersion = number;
export type Type = string;

/**
 * Top-level, serialisable IR graph for an Emergent Flow pipeline.
 *
 * Attributes
 * ----------
 * schema_version:
 *     Embedded schema version (default: CURRENT_SCHEMA_VERSION).  Allows
 *     loaders to detect and reject stale or future graphs.
 * paradigm:
 *     Graph-level paradigm tag (default: FUNCTIONAL).  Combined with
 *     per-node ``paradigm``, this drives codegen/execution branching.
 * name:
 *     Optional human-friendly label for the graph.
 * nodes:
 *     CRDT-friendly id→Node map.  Keys MUST equal ``node.id``.
 * edges:
 *     CRDT-friendly id→Edge map.  Keys MUST equal ``edge.id``.
 */
export interface Graph {
  edges?: Edges;
  name?: Name;
  nodes?: Nodes;
  paradigm?: Paradigm1;
  schema_version?: SchemaVersion;
}
export interface Edges {
  [k: string]: Edge;
}
/**
 * An edge connecting an OUT port on a source node to an IN port on a target node.
 *
 * Edges reference endpoints by id (node_id + port_id) for CRDT-friendliness,
 * not by object reference. Each edge has a unique stable id.
 *
 * Attributes:
 *     id: Stable unique identifier for this edge.
 *     source: PortRef identifying the OUT-side endpoint.
 *     target: PortRef identifying the IN-side endpoint.
 *     type_compatible: Optional type-compatibility metadata. None means "not yet
 *         checked" (or unknown/unregistered token). Populated by
 *         ``ef.apply_type_compatibility`` from a ``ef.validate`` result, recording
 *         whether source/target data-type tokens were found compatible.
 *
 * Note: Structural validation of whether referenced nodes/ports exist is handled
 * by the Graph model (Task 07), which has full node/port context.
 */
export interface Edge {
  id?: Id;
  source: PortRef;
  target: PortRef1;
  type_compatible?: TypeCompatible;
}
/**
 * The OUT-side endpoint.
 */
export interface PortRef {
  node_id: NodeId;
  port_id: PortId;
}
/**
 * The IN-side endpoint.
 */
export interface PortRef1 {
  node_id: NodeId;
  port_id: PortId;
}
export interface Nodes {
  [k: string]: Node;
}
/**
 * A typed, parameterised node in the Emergent Flow graph IR.
 *
 * Attributes
 * ----------
 * id:
 *     Stable unique identifier (auto-generated via ``new_id()``).
 * type:
 *     Node type/family key, e.g. ``"data.load_csv"`` (required, non-empty).
 * label:
 *     Optional human-friendly display label.
 * paradigm:
 *     Which execution paradigm this node belongs to (default: FUNCTIONAL).
 * params:
 *     Typed parameter values attached to this node.
 * ports:
 *     The node's in/out connection points.
 * position:
 *     Canvas coordinates (default: origin ``(0.0, 0.0)``).
 * group_id:
 *     ID of the parent group/composite node this node belongs to, or
 *     ``None`` if this is a top-level node.
 * subgraph:
 *     Optional inner graph for composite/module/agent nodes (Option A
 *     nesting from ADR 0003).  ``None`` for leaf nodes.  Forward-ref to
 *     ``Graph``; resolved by ``Node.model_rebuild()`` in Task 07
 *     (``emergentflow/ir/graph.py``).
 */
export interface Node {
  group_id?: GroupId;
  id?: Id1;
  label?: Label;
  paradigm?: Paradigm;
  params?: Params;
  ports?: Ports;
  position?: Position;
  subgraph?: Graph1 | null;
  type: Type;
}
/**
 * A single typed, defaulted, serializable parameter on an IR node.
 *
 * Fields
 * ------
 * name:
 *     Non-empty parameter name.
 * type_token:
 *     Declared-type label (e.g. ``"str"``, ``"int"``, ``"DataFrame"``). A
 *     descriptive label for the param value, distinct from the port
 *     ``data_type`` tokens the connection type system validates.
 * value:
 *     Current serializable value.  Defaults to ``None``.
 * default:
 *     Default serializable value.  Defaults to ``None``.
 */
export interface Param {
  default?:
    | (string | number | boolean | null)
    | ArtifactRef
    | ParamValue[]
    | {
        [k: string]: ParamValue;
      };
  name: Name1;
  type_token: TypeToken;
  value?:
    | (string | number | boolean | null)
    | ArtifactRef
    | ParamValue[]
    | {
        [k: string]: ParamValue;
      };
}
/**
 * Reference to a large artifact stored outside the IR graph.
 *
 * Deliberately carries *no* bytes — only a location URI and an optional
 * media-type hint.  Embedding artifact bytes in the IR is forbidden by
 * ADR 0004.
 *
 * The ``kind`` field is a fixed discriminator tag (``"artifact_ref"``). It is
 * always emitted on serialization so that an ArtifactRef can be distinguished
 * from a plain mapping that happens to share its shape (e.g. a config dict with
 * a ``uri`` key). ``ParamValue`` uses it to route deserialization, which keeps
 * JSON round-trips lossless. It defaults, so construction stays ``ArtifactRef(uri=...)``.
 */
export interface ArtifactRef {
  kind?: Kind;
  media_type?: MediaType;
  uri: Uri;
}
/**
 * A typed connection point on a node.
 *
 * Attributes:
 *     id: Stable unique identifier (auto-generated via new_id()).
 *     name: Port name, unique within its node (required, non-empty).
 *     direction: IN or OUT (required).
 *     data_type: Data-type token (default "any"); validated against the type
 *         registry and resolved by inference during ``ef.validate``.
 *     cardinality: How many edges may attach (ONE or MANY; default ONE).
 *     label: Optional human-friendly display label for the port, copied from
 *         the originating ``PortSpec`` at instantiation time. Falls back to
 *         ``name`` for display when unset.
 */
export interface Port {
  cardinality?: Cardinality;
  data_type?: DataType;
  direction: Direction;
  id?: Id2;
  label?: Label1;
  name: Name2;
}
/**
 * 2-D canvas coordinates for a node's visual placement.
 */
export interface Position {
  x?: X;
  y?: Y;
}
/**
 * Top-level, serialisable IR graph for an Emergent Flow pipeline.
 *
 * Attributes
 * ----------
 * schema_version:
 *     Embedded schema version (default: CURRENT_SCHEMA_VERSION).  Allows
 *     loaders to detect and reject stale or future graphs.
 * paradigm:
 *     Graph-level paradigm tag (default: FUNCTIONAL).  Combined with
 *     per-node ``paradigm``, this drives codegen/execution branching.
 * name:
 *     Optional human-friendly label for the graph.
 * nodes:
 *     CRDT-friendly id→Node map.  Keys MUST equal ``node.id``.
 * edges:
 *     CRDT-friendly id→Edge map.  Keys MUST equal ``edge.id``.
 */
export interface Graph1 {
  edges?: Edges;
  name?: Name;
  nodes?: Nodes;
  paradigm?: Paradigm1;
  schema_version?: SchemaVersion;
}
