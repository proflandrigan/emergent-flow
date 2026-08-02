"""
emergentflow.validity.runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Runs the registered validity rule pack over a graph (Epic 17).

``run_validity_checks`` is the pure function the validator hook
(``emergentflow.codegen.validation``) calls: it iterates every registered rule
in sorted id order, skips rules whose ``applies_when`` gate is False, runs the
rest, and returns every finding in a deterministic order (rule id, then node id
ascending per rule -- rules must sort their own findings).
"""

from __future__ import annotations

from emergentflow.ir import Graph

from .contract import ValidityFinding
from .registry import ValidityRuleRegistry
from .registry import registry as default_rule_registry


def run_validity_checks(
    graph: Graph,
    *,
    rule_registry: ValidityRuleRegistry | None = None,
) -> list[ValidityFinding]:
    """Run the registered validity rules over *graph* and return all findings.

    Deterministic: rules in sorted id order; each rule's findings appended in
    the order that rule returned them (rules must emit a stable order). Pure --
    no I/O, no global mutation -- so the same graph always yields the same
    findings and the result is golden-testable.

    Args:
        graph: The graph to check.
        rule_registry: The :class:`ValidityRuleRegistry` to use. Defaults to
            the package singleton.

    Returns:
        A list of :class:`ValidityFinding`, in rule-id order.
    """
    if rule_registry is None:
        rule_registry = default_rule_registry
    findings: list[ValidityFinding] = []
    for rule in rule_registry.all():
        if not rule.applies_when(graph):
            continue
        findings.extend(rule().check(graph))
    return findings
