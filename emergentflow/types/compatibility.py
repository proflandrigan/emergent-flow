"""
emergentflow.types.compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure connection-compatibility rules engine (Epic 3, Story 3).

Two pure, deterministic, reason-bearing functions decide whether one port may
feed another:

- :func:`is_compatible` — three-valued type compatibility (``COMPATIBLE`` /
  ``INCOMPATIBLE`` / ``UNKNOWN``) between an OUT-port type token and an IN-port
  type token, per the nominal model of ADR 0011.
- :func:`check_cardinality` — whether an IN port's
  :class:`~emergentflow.ir.common.Cardinality` permits the number of inbound edges
  targeting it (``ONE`` rejects a second edge; ``MANY`` permits fan-in).

Both functions are **pure**: output is a function of their arguments alone, with
no I/O and no global state (the type registry is passed in explicitly). This is
what lets the same rules feed golden tests, ship to the frontend as data
(ADR 0012 — the algorithm here is re-implementable client-side over the
registry's serialized catalog), and later run inside Epic 6's sandbox unchanged.

Compatibility precedence (ADR 0011, decision 2): wildcard ``"any"`` on either
side wins first; then an unregistered token on either side yields ``UNKNOWN``
(warn, don't block) — so even an exact match between two *unregistered* tokens is
``UNKNOWN``; then exact token match; then a registered subtype edge; otherwise
``INCOMPATIBLE``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from emergentflow.ir.common import Cardinality
from emergentflow.types.registry import TOP_TYPE, TypeRegistry
from emergentflow.types.registry import registry as default_registry


class Compatibility(str, Enum):
    """Three-valued verdict for a type-compatibility check (ADR 0011)."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class CompatibilityResult(BaseModel):
    """Reason-bearing result of :func:`is_compatible`.

    Attributes:
        verdict: The three-valued :class:`Compatibility` outcome.
        reason: Human-readable explanation naming the expected-vs-actual tokens,
            stable enough for golden tests and the canvas's "why is this edge
            red" affordance.
        source_type: The OUT-port (upstream) type token that was checked.
        target_type: The IN-port (downstream) type token that was checked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Compatibility
    reason: str
    source_type: str
    target_type: str


class CardinalityResult(BaseModel):
    """Reason-bearing result of :func:`check_cardinality`.

    Attributes:
        ok: ``True`` if the inbound-edge count satisfies the cardinality.
        reason: Human-readable explanation, stable for golden tests.
        cardinality: The IN port's declared cardinality that was checked.
        inbound_count: The number of inbound edges targeting the IN port.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    reason: str
    cardinality: Cardinality
    inbound_count: int


def is_compatible(
    source_type: str,
    target_type: str,
    *,
    registry: TypeRegistry = default_registry,
) -> CompatibilityResult:
    """Decide whether OUT-port type *source_type* may feed IN-port type *target_type*.

    Pure and deterministic: the verdict depends only on the arguments (including
    the explicitly-passed *registry*), per ADR 0011. Precedence:

    1. **wildcard** — either side is ``"any"`` -> ``COMPATIBLE``;
    2. **unknown** — either side is not registered -> ``UNKNOWN`` (warn), even on
       an exact match of two unregistered tokens;
    3. **exact** — ``source_type == target_type`` -> ``COMPATIBLE``;
    4. **subtype** — *source_type* is a registered transitive subtype of
       *target_type* -> ``COMPATIBLE``;
    5. otherwise -> ``INCOMPATIBLE``.

    Args:
        source_type: The upstream OUT-port data-type token.
        target_type: The downstream IN-port data-type token.
        registry: The type registry to resolve registration and subtype facts
            against. Defaults to the package singleton; tests pass their own.

    Returns:
        A :class:`CompatibilityResult` with the verdict and a token-naming reason.
    """
    # 1. Wildcard: "any" on either side connects to/from anything (warns nowhere).
    if target_type == TOP_TYPE:
        return CompatibilityResult(
            verdict=Compatibility.COMPATIBLE,
            reason=(
                f"compatible: target type is the wildcard '{TOP_TYPE}', "
                f"which accepts any source type (source '{source_type}')"
            ),
            source_type=source_type,
            target_type=target_type,
        )
    if source_type == TOP_TYPE:
        return CompatibilityResult(
            verdict=Compatibility.COMPATIBLE,
            reason=(
                f"compatible: source type is the wildcard '{TOP_TYPE}', "
                f"which connects to any target type (target '{target_type}')"
            ),
            source_type=source_type,
            target_type=target_type,
        )

    # 2. Unknown: a token we were never told about; decline to judge (warn).
    source_known = registry.is_registered(source_type)
    target_known = registry.is_registered(target_type)
    if not source_known or not target_known:
        if not source_known and not target_known and source_type != target_type:
            detail = f"types '{source_type}' and '{target_type}' are not registered"
        elif not source_known and not target_known:
            detail = f"type '{source_type}' is not registered"
        elif not source_known:
            detail = f"source type '{source_type}' is not registered"
        else:
            detail = f"target type '{target_type}' is not registered"
        return CompatibilityResult(
            verdict=Compatibility.UNKNOWN,
            reason=(
                f"unknown: {detail}, so compatibility cannot be determined "
                f"(source '{source_type}', target '{target_type}')"
            ),
            source_type=source_type,
            target_type=target_type,
        )

    # 3. Exact token match.
    if source_type == target_type:
        return CompatibilityResult(
            verdict=Compatibility.COMPATIBLE,
            reason=f"compatible: exact type match ('{source_type}')",
            source_type=source_type,
            target_type=target_type,
        )

    # 4. Registered (transitive) subtype.
    if registry.is_subtype(source_type, target_type):
        return CompatibilityResult(
            verdict=Compatibility.COMPATIBLE,
            reason=(
                f"compatible: source '{source_type}' is a registered subtype "
                f"of target '{target_type}'"
            ),
            source_type=source_type,
            target_type=target_type,
        )

    # 5. Both known, unrelated.
    return CompatibilityResult(
        verdict=Compatibility.INCOMPATIBLE,
        reason=f"incompatible: target expects '{target_type}', but source produces '{source_type}'",
        source_type=source_type,
        target_type=target_type,
    )


def check_cardinality(
    cardinality: Cardinality,
    inbound_count: int,
    *,
    port_name: str | None = None,
) -> CardinalityResult:
    """Decide whether *inbound_count* edges satisfy an IN port's *cardinality*.

    Pure and deterministic. ``Cardinality.ONE`` permits at most one inbound edge;
    a second inbound edge is a violation. ``Cardinality.MANY`` permits fan-in of
    any number of inbound edges.

    Args:
        cardinality: The IN port's declared cardinality.
        inbound_count: The number of inbound edges targeting the IN port.
        port_name: Optional IN-port name, woven into the reason when provided.

    Returns:
        A :class:`CardinalityResult` with ``ok`` and a reason.
    """
    where = f"port '{port_name}' " if port_name else ""
    if cardinality == Cardinality.ONE and inbound_count > 1:
        return CardinalityResult(
            ok=False,
            reason=(
                f"cardinality violation: {where}IN port with cardinality 'one' accepts "
                f"a single inbound edge but has {inbound_count}"
            ),
            cardinality=cardinality,
            inbound_count=inbound_count,
        )
    if cardinality == Cardinality.ONE:
        return CardinalityResult(
            ok=True,
            reason=(
                f"ok: {where}IN port with cardinality 'one' has "
                f"{inbound_count} inbound edge(s) (max 1)"
            ),
            cardinality=cardinality,
            inbound_count=inbound_count,
        )
    return CardinalityResult(
        ok=True,
        reason=(
            f"ok: {where}IN port with cardinality 'many' permits fan-in "
            f"({inbound_count} inbound edge(s))"
        ),
        cardinality=cardinality,
        inbound_count=inbound_count,
    )
