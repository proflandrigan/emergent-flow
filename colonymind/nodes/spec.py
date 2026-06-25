"""
colonymind.nodes.spec
~~~~~~~~~~~~~~~~~~~~~~
The *serializable* half of the node-definition contract (Epic 1, Story 3).

A node definition has two natures (see ADR 0005):

  1. Declarative metadata — ports, typed params, defaults, validation hints,
     version.  This must round-trip to JSON so the frontend can render a node's
     configuration UI *with no Python present* (the same constraint that drove
     the IR design in Story 2).
  2. Python behaviour — codegen, executor, type-inference.  These are callables
     and live in :mod:`colonymind.nodes.contract`; they never serialize.

This module holds nature (1).  ``NodeSpec`` is the complete JSON-able descriptor
a :class:`~colonymind.nodes.contract.NodeDefinition` exposes via ``to_spec()``;
it is what the registry (Story 4) indexes and the Epic 4 config UI consumes.

Relationship to the IR (``colonymind.ir``)
------------------------------------------
The IR models (``Port``, ``Param``) describe a node *instance* placed on the
canvas — they carry stable ids minted per instance.  The specs here are the
*templates* for a node *type*: they carry no ids (ids are assigned when a
definition is instantiated into an IR ``Node``; see ``NodeDefinition.instantiate``).
``PortSpec`` mirrors ``ir.Port`` minus the id; ``ParamSpec`` mirrors ``ir.Param``
plus authoring metadata (``required``, ``label``, ``help``, validation ``hints``).
"""

from __future__ import annotations

from pydantic import Field, field_validator

from colonymind.ir.common import Cardinality, Direction, IRModel, Paradigm
from colonymind.ir.params import ParamValue

# ---------------------------------------------------------------------------
# PortSpec — declared connection point on a node *type*
# ---------------------------------------------------------------------------


class PortSpec(IRModel):
    """A declared port on a node type (the template for an IR ``Port``).

    Mirrors ``colonymind.ir.port.Port`` but carries no ``id`` — ids are minted
    per instance when a definition is instantiated.  ``required`` only constrains
    IN ports (an OUT port is a value the node produces, never "missing").

    Fields
    ------
    name:
        Port name, unique among the node's ports of the *same direction*
        (required, non-empty).  IN and OUT ports may share a name — ``execute``
        keys its ``inputs`` by IN-port name and its return by OUT-port name, so
        the two namespaces are independent (e.g. ``clean.impute_missing`` has an
        IN ``table`` and an OUT ``table``).
    direction:
        IN or OUT (required).
    data_type:
        Data-type token (default ``"any"``); validated against the type registry
        and resolved by inference during ``cm.validate``.
    cardinality:
        How many edges may attach (ONE or MANY; default ONE).
    required:
        For IN ports, whether an incoming edge must be connected (default True).
        Ignored for OUT ports.
    label:
        Optional human-friendly display label for the port.
    help:
        Optional one-line description (shown in tooltips / docs).
    """

    name: str
    direction: Direction
    data_type: str = "any"
    cardinality: Cardinality = Cardinality.ONE
    required: bool = True
    label: str | None = None
    help: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "PortSpec.name must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v


# ---------------------------------------------------------------------------
# ValidationHints — declarative constraints + UI affordances for a param
# ---------------------------------------------------------------------------


class ValidationHints(IRModel):
    """Optional, declarative validation + UI hints for a parameter.

    Every field is optional; an unset field imposes no constraint.  These are
    consumed at two points:

      * the Epic 4 config UI, to render the right widget and client-side guards;
      * ``NodeDefinition.validate_node``, to check an instance's param values
        against the declared constraints at author/load time.

    Fields
    ------
    min, max:
        Inclusive numeric bounds (applied to int/float values).
    step:
        Numeric step increment hint (for slider/number widgets).
    choices:
        Allowed values — when set, a value must be one of these (enum/select).
    min_length, max_length:
        Inclusive length bounds for string or list values.
    pattern:
        Regular expression a string value must fully match.
    widget:
        UI widget hint, e.g. ``"text"``, ``"number"``, ``"select"``,
        ``"slider"``, ``"checkbox"``, ``"file"``.  Advisory only.
    """

    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[ParamValue] | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    widget: str | None = None


# ---------------------------------------------------------------------------
# ParamSpec — declared typed parameter on a node *type*
# ---------------------------------------------------------------------------


class ParamSpec(IRModel):
    """A declared parameter on a node type (the template for an IR ``Param``).

    Mirrors ``colonymind.ir.params.Param`` (``name``, ``type_token``, ``default``)
    and adds the authoring metadata the config UI needs: whether the param is
    ``required``, a display ``label`` and ``help`` string, and validation
    ``hints``.

    Fields
    ------
    name:
        Non-empty parameter name (unique within the node).
    type_token:
        Declared-type label for the param value (e.g. ``"str"``, ``"int"``,
        ``"DataFrame"``). Distinct from the port ``data_type`` tokens the
        connection type system validates.
    default:
        Default serializable value used when the instance leaves it unset.
    required:
        Whether a value must be supplied (no usable default).  Default False.
    label:
        Optional human-friendly display label.
    help:
        Optional one-line description (shown in the config UI / docs).
    hints:
        Optional :class:`ValidationHints` (constraints + widget choice).
    """

    name: str
    type_token: str
    default: ParamValue = None
    required: bool = False
    label: str | None = None
    help: str | None = None
    hints: ValidationHints | None = None

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "ParamSpec.name must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v

    @field_validator("type_token")
    @classmethod
    def type_token_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "ParamSpec.type_token must be a non-empty, non-whitespace string; "
                "received an empty or blank value."
            )
        return v


# ---------------------------------------------------------------------------
# NodeSpec — the complete serializable descriptor of a node *type*
# ---------------------------------------------------------------------------


class NodeSpec(IRModel):
    """The full declarative descriptor of a node type.

    This is the JSON-able object a ``NodeDefinition`` emits via ``to_spec()``.
    The registry (Story 4) indexes it; the Epic 4 config UI renders from it; the
    frontend needs nothing else (no Python) to draw and configure the node.

    Fields
    ------
    type:
        Catalog key, e.g. ``"data.load_csv"``.  Matches ``ir.Node.type`` and is
        the registry lookup key (required, non-empty).
    version:
        Per-node catalog version (see ``NodeDefinition.version``).  Distinct from
        ``Graph.schema_version``: this tracks one node type's contract, the other
        tracks the IR wire format.
    family:
        Coarse grouping for catalog/UI organisation, e.g. ``"data"``, ``"stats"``.
    label:
        Human-friendly display name.
    category:
        Human-friendly palette grouping, e.g. "Ingest", "Transform".
    description:
        One-line description shown in the palette / tooltips.
    paradigm:
        Which execution paradigm this node belongs to (ADR 0003).
    ports:
        Declared ports (templates for the instance's IR ports).
    params:
        Declared typed params (templates for the instance's IR params).
    """

    type: str
    version: int = 1
    family: str
    label: str
    category: str = ""
    description: str = ""
    paradigm: Paradigm = Paradigm.FUNCTIONAL
    ports: list[PortSpec] = Field(default_factory=list)
    params: list[ParamSpec] = Field(default_factory=list)

    @field_validator("type", "family", "label")
    @classmethod
    def field_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "NodeSpec.type/family/label must be non-empty, non-whitespace "
                "strings; received an empty or blank value."
            )
        return v

    @field_validator("version")
    @classmethod
    def version_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"NodeSpec.version must be a positive integer (>= 1); received {v!r}.")
        return v
