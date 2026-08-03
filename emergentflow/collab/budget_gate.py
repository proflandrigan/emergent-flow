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

    This is a simple heuristic: count the number of LLM call nodes
    and multiply by an average cost per call. A more sophisticated
    implementation would analyze the graph structure and node params.

    For now, return 0.0 as a placeholder — the actual cost tracking
    happens via BudgetClient during execution.
    """
    # Placeholder: in a real implementation, we'd analyze the graph
    # to estimate cost based on LLM nodes, expected token counts, etc.
    return 0.0


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