"""
emergentflow.validity.contract
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Validity rule contract (Epic 17).

A :class:`ValidityRule` is a pure, static check over a ``Graph``'s topology. It
mirrors the node registry's shape (class-level metadata + behavior methods, see
``emergentflow.nodes.contract``): each rule declares an id, severity,
confidence, title, rationale, and an optional ``applies_when`` gate, and
implements ``check(graph) -> list[ValidityFinding]``.

A :class:`ValidityFinding` is the lightweight, self-contained finding shape a
rule produces; the validator hook (``emergentflow.codegen.validation``)
converts it into a ``Diagnostic`` carrying ``rule_id`` and ``related_node_ids``
so findings ride the existing diagnostics channel (no new report type).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.ir import Graph

#: Severities a rule may declare. Warnings by default; only rules that are
#: decidable-without-inference may be errors (a false positive that blocks a run
#: destroys trust in the whole pack).
SEVERITIES: tuple[str, ...] = ("error", "warning")

#: Confidence a rule declares about its own precision.
CONFIDENCE: tuple[str, ...] = ("high", "medium", "low")


class ValidityFinding(BaseModel):
    """A single rule finding: what tripped, on which nodes.

    Attributes:
        rule_id: the rule's machine-readable id (e.g. ``"fit_before_split"``).
        severity: ``"error"`` or ``"warning"``.
        message: human-readable explanation.
        node_id: the primary implicated node, when the finding is about a node.
        related_node_ids: other nodes implicated alongside ``node_id``, for
            findings about a relationship between two nodes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    severity: str
    message: str
    node_id: str | None = None
    related_node_ids: list[str] = Field(default_factory=list)


class ValidityRule(ABC):
    """Abstract base for a validity rule: class metadata + a ``check`` method.

    Subclasses declare the metadata as class attributes and implement
    :meth:`check`. Metadata mirrors the node registry's class-level style.
    """

    #: Machine-readable rule id, e.g. ``"fit_before_split"``. MUST be unique.
    id: ClassVar[str] = ""
    #: One of ``SEVERITIES``.
    severity: ClassVar[str] = ""
    #: One of ``CONFIDENCE``.
    confidence: ClassVar[str] = ""
    #: Human-readable title for the problems list.
    title: ClassVar[str] = ""
    #: Markdown rationale: why the topology it detects is a validity failure,
    #: and its known false-positive shape.
    rationale: ClassVar[str] = ""

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        """Cheap pre-gate: whether the rule is worth running on *graph*.

        Defaults to always. Subclasses may override to skip cheaply (e.g. only
        run when the graph contains a split node).
        """
        return True

    @abstractmethod
    def check(self, graph: Graph) -> list[ValidityFinding]:
        """Return every finding for *graph*.

        Pure and deterministic: no I/O, no global state; findings sorted in a
        stable order (node id ascending) so results are golden-testable.
        """
        raise NotImplementedError
