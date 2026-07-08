"""
emergentflow.data.warehouse.params
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``ConnectionRef`` param convention (Epic 13 Story 3, ADR 0018).

A warehouse query node references a connection by a **profile name** — never a
credential (ADR 0018). That reference is a normal IR ``Param`` carrying the
``ConnectionRef`` type-token and a ``"connection"`` widget hint, so the canvas
renders a **profile picker** whose choices come from the local connection store
at design time (the IR only ever holds the chosen name). This module centralizes
the token/widget names and a builder so every query node (Story 4/5) declares the
param identically.
"""

from __future__ import annotations

from emergentflow.nodes.spec import ParamSpec, ValidationHints

#: Param ``type_token`` marking a value as a connection-profile *name* reference.
CONNECTION_REF_TOKEN = "ConnectionRef"

#: ``ValidationHints.widget`` value the canvas maps to the profile-picker control.
CONNECTION_WIDGET = "connection"


def connection_param(
    name: str = "connection",
    *,
    required: bool = True,
    label: str = "Connection",
    help: str = "The named connection profile to run against (from your local store).",
) -> ParamSpec:
    """Build the ``ParamSpec`` for a warehouse node's connection reference.

    The value is a profile *name* (ADR 0018 — never a credential). Rendered as a
    profile picker via the ``"connection"`` widget; choices are supplied by the
    local store at design time, so the IR carries only the selected name.
    """
    return ParamSpec(
        name=name,
        type_token=CONNECTION_REF_TOKEN,
        required=required,
        label=label,
        help=help,
        hints=ValidationHints(widget=CONNECTION_WIDGET),
    )
