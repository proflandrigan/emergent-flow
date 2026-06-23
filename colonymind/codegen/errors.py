"""
colonymind.codegen.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed exceptions raised by the code-generation engine's graph-analysis layer
(Epic 2, Story 2).

The hierarchy is rooted at :class:`CodegenError` so callers can catch every
codegen-layer failure with a single ``except``. Each subclass marks a specific,
actionable failure mode discovered while traversing or wiring a graph.
"""

from __future__ import annotations


class CodegenError(Exception):
    """Base class for all code-generation engine errors."""


class CycleError(CodegenError):
    """Raised when a functional-pipeline graph contains a cycle.

    Functional pipelines must be acyclic to admit a topological order. The
    message should name the nodes involved in the cycle so the author can find
    and break it.
    """


class CardinalityError(CodegenError):
    """Raised when a port's cardinality constraint is violated during wiring.

    For example, an IN port declared ``Cardinality.ONE`` that has more than one
    incoming edge feeding it.
    """


class UnboundInputError(CodegenError):
    """Raised when the whole-graph compiler finds a node's IN port with no upstream edge.

    The generated code would otherwise reference an undefined variable. The
    message should name the node and port so the author can find and fix the
    missing connection.
    """


class GraphValidationError(CodegenError):
    """Raised when the shared validation gate rejects a graph before codegen/execution.

    Epic 3, Story 6: `compile_to_code` and `execute` both call the single
    `enforce_validation_gate` (`colonymind.codegen.validation`) before doing any
    work, so the two pure functions reject the same graphs for the same reasons
    (ADR 0002 equivalence extends to rejection). The exception is raised only for
    *error*-severity diagnostics (type incompatibility, cardinality violation,
    unconnected required IN port); warnings pass through (warn-don't-block). The
    message names every offending node/edge/port so the author can find and fix
    the wiring.
    """
