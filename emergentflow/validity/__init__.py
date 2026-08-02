"""
emergentflow.validity
~~~~~~~~~~~~~~~~~~~~~
Experiment-validity static analysis (Epic 17): rules that turn ``ef.validate``
from "do these ports fit together" into "is this experiment valid". Rules are
pure, static checks over the graph IR's topology -- target leakage, temporal
leakage, train/serve skew, and metric misuse -- shipped as a versioned rule-pack
artifact (ADR 0012) and consumed by the canvas as data.

The rule registry + implementations are deliberately import-light: nothing here
imports ``emergentflow.codegen.validation``, so the validator can hook this
package without an import cycle. Findings use the local :class:`ValidityFinding`
shape; ``emergentflow.codegen.validation`` converts them to ``Diagnostic``s.
"""

from __future__ import annotations

from . import rules  # noqa: F401  (registers every in-tree validity rule)
from .contract import ValidityFinding, ValidityRule
from .registry import ValidityRuleRegistry, registry, validity_rule
from .runner import run_validity_checks
from .traversal import all_edges, downstream, reaches, upstream

__all__ = [
    "ValidityFinding",
    "ValidityRule",
    "ValidityRuleRegistry",
    "all_edges",
    "downstream",
    "reaches",
    "registry",
    "run_validity_checks",
    "upstream",
    "validity_rule",
]
