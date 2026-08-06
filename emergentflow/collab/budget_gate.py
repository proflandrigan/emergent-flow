"""
emergentflow.collab.budget_gate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Budget-triggered EXECUTE gate (Epic 17 Story 9).

When an agent-initiated run would exceed the configured budget ceiling,
auto-open an EXECUTE gate instead of executing. The gate carries the
estimated cost and reason; a human decision resumes or cancels.
"""

from __future__ import annotations

import os
from typing import Any

# Default budget ceiling in USD (can be overridden via environment variable)
DEFAULT_BUDGET_CEILING_USD = 1.0


def get_budget_ceiling() -> float:
    """Return the configured budget ceiling in USD.

    Reads from EMERGENTFLOW_BUDGET_CEILING_USD environment variable,
    or returns the default if not set.
    """
    env_value = os.environ.get("EMERGENTFLOW_BUDGET_CEILING_USD")
    if env_value is not None:
        try:
            return float(env_value)
        except ValueError:
            pass
    return DEFAULT_BUDGET_CEILING_USD


def estimate_run_cost(graph_dict: dict[str, Any]) -> float:
    """Estimate the cost of running a graph in USD.

    Counts the nodes that require a network/LLM client (Epic 17 ADR 0017 nodes:
    LLM calls, embed calls, warehouse queries) and multiplies by an average cost
    per client call. Pure local-model / data-only runs estimate to 0.0.

    The per-call cost is a heuristic default, overridable via
    ``EMERGENTFLOW_EST_COST_PER_CALL``.
    """
    from emergentflow.nodes import registry as default_node_registry

    avg_cost_per_call = float(os.environ.get("EMERGENTFLOW_EST_COST_PER_CALL", "0.001"))
    counted = 0
    for node_data in graph_dict.get("nodes", {}).values():
        node_type = node_data.get("type")
        definition_cls = default_node_registry.try_get(node_type)
        if definition_cls is None:
            # Unknown types count as cost-affecting too: conservative, never
            # under-estimate a run.
            counted += 1
            continue
        if definition_cls.required_client_kinds():
            counted += 1
    return counted * avg_cost_per_call


def check_budget_and_open_gate(
    session_id: str,
    estimated_cost: float,
    budget_ceiling: float,
) -> dict[str, Any] | None:
    """Check if estimated cost exceeds budget ceiling.

    If exceeded, auto-open an EXECUTE gate and return the gate info.
    Otherwise, return None to proceed with execution.
    """
    if estimated_cost <= budget_ceiling:
        return None

    from emergentflow.collab.gates import Gate, GateKind
    from emergentflow.collab.session import get_default_store as get_default_session_store

    store = get_default_session_store()

    # Open an EXECUTE gate with the budget info
    gate = store.open_gate(
        session_id,
        Gate(
            phase="budget_check",
            kind=GateKind.EXECUTE,
            description=(
                f"Run estimated cost (${estimated_cost:.4f}) exceeds budget ceiling "
                f"(${budget_ceiling:.4f}). Close this gate to approve execution."
            ),
        ),
    )

    return {
        "budget_exceeded": True,
        "estimated_cost": estimated_cost,
        "budget_ceiling": budget_ceiling,
        "gate_id": gate.id,
        "gate_phase": gate.phase,
        "gate_kind": gate.kind.value,
        "gate_description": gate.description,
    }
