"""
emergentflow.nodes.contract
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The node-definition contract (Epic 1, Story 3).

Every node type declares *what it is* in one consistent way so the registry
(Story 4), codegen (Epic 2), executor (Epic 2), and config UI (Epic 4) can all
consume it uniformly.  A node declares:

  * **ports** and **typed params** — via class-level ``PortSpec`` / ``ParamSpec``
    lists (the serializable half; see :mod:`emergentflow.nodes.spec`);
  * a **codegen template** — ``codegen(node) -> CodeFragment``;
  * an **executor** — ``execute(node, inputs) -> dict``;
  * a **shape/type-inference function** — ``infer_types(...)`` (optional; the
    default returns the declared OUT-port types).

See ADR 0005 for why the contract is split into a serializable spec plus
Python-only behaviour.  See ADR 0002 for the hard invariant this contract is
built to uphold: for any node, ``execute`` and the code emitted by ``codegen``
must produce equivalent results.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from emergentflow.clients import ClientKind
from emergentflow.ir.common import IRModel, Paradigm
from emergentflow.ir.node import Node, Position
from emergentflow.ir.params import Param, ParamValue
from emergentflow.ir.port import Port

from .spec import NodeSpec, ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

# ---------------------------------------------------------------------------
# CodeFragment — the unit a node's codegen emits
# ---------------------------------------------------------------------------


class CodeFragment(IRModel):
    """The Python source a single node contributes to a compiled graph.

    Structured rather than a bare string so the whole-graph compiler (Epic 2)
    can collect and de-duplicate ``imports`` across every node and concatenate
    the ``body`` fragments in topological order.

    Fields
    ------
    imports:
        Import lines this fragment needs, e.g. ``["import pandas as pd"]``.
        The compiler de-duplicates these across the graph.
    body:
        The statement(s) implementing the node, e.g.
        ``df = pd.read_csv("x.csv")``.  May reference variables bound by
        upstream fragments and should bind this node's outputs.
    """

    imports: list[str] = Field(default_factory=list)
    body: str = ""

    def render(self) -> str:
        """Return a self-contained snippet: imports, a blank line, then the body.

        Convenience for tests and single-node previews.  The real whole-graph
        compiler renders imports once for the entire graph rather than per node.
        """
        imports_block = "\n".join(self.imports)
        if imports_block and self.body:
            return f"{imports_block}\n\n{self.body}"
        return imports_block or self.body


# ---------------------------------------------------------------------------
# NodeDefinition — the contract every node type conforms to
# ---------------------------------------------------------------------------


class NodeDefinition(ABC):
    """Base class for every node type in the catalog.

    A concrete definition sets the class-level metadata attributes and
    implements ``codegen`` and ``execute`` (and, where relevant, overrides
    ``infer_types``).  The concrete helpers ``to_spec``, ``instantiate`` and
    ``validate_node`` are derived from the declared metadata and need not be
    overridden.

    Class attributes (declared by every subclass)
    ---------------------------------------------
    type:
        Catalog key, e.g. ``"data.load_csv"``.  Matches ``ir.Node.type`` and is
        the registry lookup key.
    version:
        Per-node catalog version — bump on any contract-affecting change to this
        node (params added/removed, codegen/executor semantics changed).  This is
        deliberately *distinct* from ``Graph.schema_version``: the schema version
        tracks the IR wire format for the whole graph, while ``version`` tracks
        one node type's contract.  Story 9 migrations key off both axes.
    family:
        Coarse catalog grouping, e.g. ``"data"``, ``"clean"``, ``"stats"``.
    label:
        Human-friendly display name.
    category:
        Human-friendly palette grouping, e.g. ``"Ingest"``, ``"Transform"``.
    description:
        One-line description shown in the palette / tooltips.
    paradigm:
        Execution paradigm (ADR 0003); default FUNCTIONAL.
    cacheable:
        Whether this node's outputs may be served from the on-disk execution
        cache instead of re-running ``execute``. Default ``True``. Set
        ``False`` for nodes whose ``execute`` is not a pure function of its
        params and inputs (e.g. non-deterministic LLM nodes, deferred to a
        later epic) — a cache hit for such a node would silently serve a
        stale/wrong result.
    requires_client:
        Whether this node's ``execute`` needs an injected ``LLMClient``
        (ADR 0017). Default ``False`` for every ordinary, pure node. LLM-call
        nodes (Epic 9) set this ``True``; ``emergentflow.codegen.executor.execute``
        then calls their ``execute`` with a ``client=`` keyword argument, and
        ``emergentflow.codegen.compiler.compile_to_code`` emits a ``main()``
        entry point that accepts a ``client`` parameter. Graphs containing no
        such node are completely unaffected — this is an opt-in, additive flag.
    requires:
        The set of injected-client capabilities this node needs (ADR 0018),
        e.g. ``frozenset({ClientKind.WAREHOUSE})``. Generalizes ``requires_client``
        to more than one effect type. Prefer this for new effectful nodes; the
        legacy ``requires_client`` boolean is still honored (it implies
        ``ClientKind.LLM``) via ``required_client_kinds`` so every Epic 9 LLM node
        is unchanged. Default: the empty set (a pure node needs no client).
    ports:
        Declared :class:`PortSpec` list.
    params:
        Declared :class:`ParamSpec` list.
    """

    type: ClassVar[str]
    version: ClassVar[int] = 1
    family: ClassVar[str]
    label: ClassVar[str]
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    paradigm: ClassVar[Paradigm] = Paradigm.FUNCTIONAL
    cacheable: ClassVar[bool] = True
    requires_client: ClassVar[bool] = False
    requires: ClassVar[frozenset[ClientKind]] = frozenset()
    ports: ClassVar[list[PortSpec]] = []
    params: ClassVar[list[ParamSpec]] = []

    # ------------------------------------------------------------------
    # Behaviour — implemented by concrete node definitions
    # ------------------------------------------------------------------

    @classmethod
    def required_client_kinds(cls) -> frozenset[ClientKind]:
        """Resolve the effective set of client capabilities this node needs (ADR 0018).

        Unions the declared ``requires`` capability set with the legacy
        ``requires_client`` boolean (which implies ``ClientKind.LLM``), so existing
        LLM nodes that only set ``requires_client = True`` keep meaning "needs the
        LLM client" and new nodes can declare ``requires`` directly. A pure node
        (neither set) returns the empty set.
        """
        kinds = set(cls.requires)
        if cls.requires_client:
            kinds.add(ClientKind.LLM)
        return frozenset(kinds)

    @abstractmethod
    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        """Emit the Python source implementing *node* (the codegen template).

        *ctx* (ADR 0009) supplies the variable name bound to each IN port
        (``ctx.in_var(port_name)``) and allocated to each OUT port
        (``ctx.out_var(port_name)``); a node asks the context for names instead
        of hardcoding them, so the whole-graph compiler can wire real graphs and
        names never collide.

        Must be the human-readable equivalent of ``execute`` for the same node
        (ADR 0002).  The output is for display, export and Git publishing; it is
        never ``exec``-ed in production.
        """

    def preview(self, node: Node) -> CodeFragment:
        """Emit a single-node code preview, with each port's variable == its name.

        Builds a trivial port-name-identity :class:`CodegenContext` and calls
        ``codegen``.  This is the canvas "show code" path (Epic 3): a node
        previewed on its own renders exactly as it did before the Story 4 binding
        contract (e.g. ``data.load_csv`` -> ``frame = ef.data.load_csv(...)``).
        The whole-graph compiler instead passes a graph-resolved context.
        """
        from emergentflow.codegen.context import CodegenContext

        return self.codegen(node, CodegenContext.preview(node))

    @abstractmethod
    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run *node* directly over its IR.

        Parameters
        ----------
        node:
            The IR node instance being executed (source of param values).
        inputs:
            Values arriving on the node's IN ports, keyed by IN-port name.

        Returns
        -------
        dict
            Output values keyed by OUT-port name.
        """

    def infer_types(self, node: Node, input_types: dict[str, str]) -> dict[str, str]:
        """Infer the data-type token produced on each OUT port.

        The default returns each OUT port's declared ``data_type``.  Override for
        nodes whose output type depends on inputs or params; the whole-graph
        inference pass threads resolved upstream types in through ``input_types``
        and feeds the result to ``ef.validate`` (see ``docs/type-system-spec.md``).
        Per-dimension tensor shape inference is deferred to roadmap Epic 10.

        Parameters
        ----------
        node:
            The IR node instance.
        input_types:
            Data-type tokens arriving on IN ports, keyed by IN-port name.

        Returns
        -------
        dict
            Data-type token per OUT-port name.
        """
        return {
            port.name: port.data_type for port in type(self).ports if port.direction.value == "out"
        }

    # ------------------------------------------------------------------
    # Derived helpers — not overridden by subclasses
    # ------------------------------------------------------------------

    def to_spec(self) -> NodeSpec:
        """Return the serializable :class:`NodeSpec` for this node type.

        This is the JSON-able descriptor the registry indexes and the config UI
        renders from — it carries only the declarative metadata, never the
        Python behaviour.
        """
        cls = type(self)
        return NodeSpec(
            type=cls.type,
            version=cls.version,
            family=cls.family,
            label=cls.label,
            category=cls.category,
            description=cls.description,
            paradigm=cls.paradigm,
            ports=list(cls.ports),
            params=list(cls.params),
        )

    def instantiate(
        self,
        *,
        label: str | None = None,
        position: Position | None = None,
        **param_overrides: ParamValue,
    ) -> Node:
        """Build a fresh IR :class:`~emergentflow.ir.node.Node` from this definition.

        Ports are minted from the declared :class:`PortSpec` list and params from
        the declared :class:`ParamSpec` list, taking each value from
        ``param_overrides`` when supplied and otherwise from the spec default.
        Fresh stable ids are assigned to the node and every port.

        Raises
        ------
        ValueError
            If ``param_overrides`` names a param this definition does not declare.
        """
        cls = type(self)

        declared = {p.name for p in cls.params}
        unknown = set(param_overrides) - declared
        if unknown:
            raise ValueError(
                f"{cls.type!r}: unknown param override(s) {sorted(unknown)!r}; "
                f"declared params are {sorted(declared)!r}."
            )

        ports = [
            Port(
                name=ps.name,
                direction=ps.direction,
                data_type=ps.data_type,
                cardinality=ps.cardinality,
            )
            for ps in cls.ports
        ]
        params = [
            Param(
                name=ps.name,
                type_token=ps.type_token,
                value=param_overrides.get(ps.name, ps.default),
                default=ps.default,
            )
            for ps in cls.params
        ]

        return Node(
            type=cls.type,
            label=label if label is not None else cls.label,
            paradigm=cls.paradigm,
            ports=ports,
            params=params,
            position=position if position is not None else Position(),
        )

    def validate_node(self, node: Node) -> list[str]:
        """Validate an IR *node*'s params against this definition's contract.

        Returns a (possibly empty) list of human-readable error messages — the
        same checks the Epic 4 config UI surfaces to the author.  Checks:

          * ``node.type`` matches this definition's ``type``;
          * every required param has a non-None value;
          * no param is present that the definition does not declare;
          * each value satisfies its :class:`ValidationHints` (choices, numeric
            min/max, string/list length, regex pattern).

        Port/edge wiring is validated at the graph level (``ir.Graph``), not here.
        """
        cls = type(self)
        errors: list[str] = []

        if node.type != cls.type:
            errors.append(f"node.type {node.type!r} does not match definition type {cls.type!r}.")

        specs = {ps.name: ps for ps in cls.params}
        values = {p.name: p.value for p in node.params}

        for extra in set(values) - set(specs):
            errors.append(f"param {extra!r} is not declared by {cls.type!r}.")

        for name, ps in specs.items():
            present = name in values
            value = values.get(name)

            if ps.required and (not present or value is None):
                errors.append(f"required param {name!r} is missing or None.")
                continue
            if not present or value is None:
                continue  # optional + unset → nothing to check

            errors.extend(_check_hints(name, value, ps))

        return errors


# ---------------------------------------------------------------------------
# Validation-hint checking
# ---------------------------------------------------------------------------


def _check_hints(name: str, value: Any, ps: ParamSpec) -> list[str]:
    """Return error messages for *value* violating ``ps.hints`` (empty if OK)."""
    hints = ps.hints
    if hints is None:
        return []

    errors: list[str] = []

    if hints.choices is not None and value not in hints.choices:
        errors.append(f"param {name!r} value {value!r} is not one of {hints.choices!r}.")

    if isinstance(value, bool):
        # bool is a subclass of int; never treat it as a numeric for min/max.
        pass
    elif isinstance(value, (int, float)):
        if hints.min is not None and value < hints.min:
            errors.append(f"param {name!r} value {value!r} is below min {hints.min!r}.")
        if hints.max is not None and value > hints.max:
            errors.append(f"param {name!r} value {value!r} is above max {hints.max!r}.")

    if isinstance(value, (str, list)):
        length = len(value)
        if hints.min_length is not None and length < hints.min_length:
            errors.append(f"param {name!r} length {length} is below min_length {hints.min_length}.")
        if hints.max_length is not None and length > hints.max_length:
            errors.append(f"param {name!r} length {length} is above max_length {hints.max_length}.")

    if (
        hints.pattern is not None
        and isinstance(value, str)
        and re.fullmatch(hints.pattern, value) is None
    ):
        errors.append(f"param {name!r} value {value!r} does not match pattern {hints.pattern!r}.")

    return errors
