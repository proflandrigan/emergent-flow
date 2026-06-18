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
