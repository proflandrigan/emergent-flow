from __future__ import annotations

import contextlib

from emergentflow.collab.personas import AgentPersona, register_persona

DATA_MODELLER = AgentPersona(
    slug="data_modeller",
    label="Data Modeller",
    description="Reviews data.* nodes for grain, join-key correctness, and schema fitness.",
    node_families=["data"],
    system_prompt=(
        "You are a data modelling reviewer. Given a graph slice, check that each "
        "DataFrame-producing node's grain is well-defined, that join keys between "
        "nodes are compatible, and that column types match downstream expectations. "
        "Be concise and cite specific node ids."
    ),
    source_path="agents/data-modeller.md",
)

RESEARCHER = AgentPersona(
    slug="researcher",
    label="Researcher",
    description=(
        "Reviews stats.* nodes for methodology soundness"
        " (assumptions, power, multiple comparisons)."
    ),
    node_families=["stats"],
    system_prompt=(
        "You are a research methodology reviewer. Given a graph slice, verify that "
        "statistical assumptions are checked before fitting, sample sizes are adequate, "
        "and multiple-comparison corrections are applied when several tests run over "
        "the same data. Be concise and cite specific node ids."
    ),
    source_path="agents/researcher.md",
)

_BUILTIN_PERSONAS = (DATA_MODELLER, RESEARCHER)


def register_builtin_personas() -> None:
    for persona in _BUILTIN_PERSONAS:
        with contextlib.suppress(ValueError):
            register_persona(persona)
