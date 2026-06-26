"""
emergentflow.types.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Emergent Flow type registry: a nominal type catalog with a subtype relation.

This module defines a nominal type system where types are identified by string
tokens. The only relationships between types are token equality and declared
``(subtype, supertype)`` edges. ``"any"`` is the explicit TOP/wildcard type —
every type is implicitly a subtype of ``"any"``, and ``"any"`` is always present
in every registry.

Compatibility checking (the three-valued ``is_compatible`` function) is Epic 3
Story 3 and lives elsewhere; this file owns the catalog data structure, its
subtype-graph queries, JSON serialization (:meth:`TypeRegistry.to_dict`), and
out-of-core plugin discovery.
"""

from __future__ import annotations

import importlib.metadata

from pydantic import field_validator

from emergentflow.ir.common import IRModel

TOP_TYPE = "any"

#: The entry-point group third-party packages publish type tokens under, mirroring
#: the ``emergentflow.nodes`` group used for out-of-core node definitions (ADR 0006).
ENTRY_POINT_GROUP = "emergentflow.types"


class TypeDef(IRModel):
    """A registered data-type token plus optional declared supertypes.

    In a nominal type system, a type is just a string token; the only
    relationships are token equality and declared ``(subtype, supertype)`` edges.

    Attributes:
        token: The type-token identifier (e.g. ``"DataFrame"``).
        description: Optional human-readable description.
        supertypes: Declared direct supertype tokens. May reference tokens not
            (yet) registered; forward references are allowed. Note that tuple
            order is part of model identity (``__eq__``), so idempotent
            re-registration requires the same order — declare supertypes
            consistently across plugin versions.
    """

    token: str
    description: str = ""
    supertypes: tuple[str, ...] = ()

    @field_validator("token")
    @classmethod
    def validate_token(cls, token: str) -> str:
        """Validate that the type token is a non-empty, non-whitespace string."""
        if not token or not token.strip():
            raise ValueError(
                f"TypeDef.token must be a non-empty, non-whitespace string; got {token!r}"
            )
        return token


class TypeRegistry:
    """A catalog of :class:`TypeDef` objects with a subtype relation.

    This is a nominal type system: a type is just a string token; the only
    relationships are token equality and declared ``(subtype, supertype)`` edges.
    ``"any"`` is the explicit TOP type — every type is implicitly a subtype of
    ``"any"``, which is always present in every registry.
    """

    def __init__(self) -> None:
        """Initialise the registry, seeding it with the ever-present TOP type."""
        self._defs: dict[str, TypeDef] = {}
        self._defs[TOP_TYPE] = TypeDef(
            token=TOP_TYPE,
            description="The top/wildcard type; every type is implicitly a subtype of 'any'.",
        )

    def register(self, typedef: TypeDef) -> TypeDef:
        """Register *typedef* and return it.

        Fail-fast checks:

        1. ``typedef`` must be a :class:`TypeDef` instance.
        2. Duplicate key: if ``typedef.token`` is already registered to an
           **equal** ``TypeDef``, return it unchanged (idempotent no-op). If
           registered to a **different** ``TypeDef``, raise ``ValueError``.
        3. Cycle detection: registering ``typedef`` must not create a cycle in
           the subtype graph (a self-loop, or a token reachable as a transitive
           supertype of one of its declared supertypes).

        Raises:
            ValueError: If the typedef is not a ``TypeDef``, conflicts with an
                existing registration, or would create a cycle.
        """
        if not isinstance(typedef, TypeDef):
            raise ValueError(f"Expected TypeDef instance; got {type(typedef).__name__}")

        token = typedef.token
        if token in self._defs:
            existing = self._defs[token]
            if existing == typedef:
                return typedef  # idempotent re-registration
            raise ValueError(
                f"TypeDef with token {token!r} already registered as {existing!r}; "
                f"cannot register {typedef!r}"
            )

        # Self-loop is a trivial cycle.
        if token in typedef.supertypes:
            raise ValueError(f"Self-loop detected: {token!r} cannot be a supertype of itself")

        # Simulate the addition (without mutating self._defs) and walk the
        # subtype graph from each declared supertype, looking for a path back to
        # the new token.
        temp_defs = dict(self._defs)
        temp_defs[token] = typedef

        def _walk(start: str) -> None:
            visited: set[str] = set()
            stack = [start]
            while stack:
                current = stack.pop()
                if current == token:
                    raise ValueError(
                        f"Registering {token!r} would create a subtype cycle via {start!r}"
                    )
                if current in visited:
                    continue
                visited.add(current)
                if current in temp_defs:
                    stack.extend(temp_defs[current].supertypes)

        for st in typedef.supertypes:
            _walk(st)

        self._defs[token] = typedef
        return typedef

    def get(self, token: str) -> TypeDef:
        """Return the registered :class:`TypeDef` for *token*.

        Raises:
            KeyError: If *token* is not registered.
        """
        try:
            return self._defs[token]
        except KeyError:
            raise KeyError(f"Type {token!r} is not registered") from None

    def try_get(self, token: str) -> TypeDef | None:
        """Return the registered :class:`TypeDef` for *token*, or ``None``."""
        return self._defs.get(token)

    def is_registered(self, token: str) -> bool:
        """Return ``True`` if *token* is registered."""
        return token in self._defs

    def supertypes_of(self, token: str, *, transitive: bool = True) -> set[str]:
        """Return the supertype tokens of *token*.

        With ``transitive=True`` (default), follow subtype edges to all
        ancestors. ``TOP_TYPE`` is always included when ``token != TOP_TYPE``
        (every type is implicitly a subtype of ``"any"``). An unregistered token
        has no declared supertypes but still gains ``TOP_TYPE``. ``TOP_TYPE``
        itself has no supertypes. The token itself is never included.
        """
        result: set[str] = set() if token == TOP_TYPE else {TOP_TYPE}

        if token not in self._defs:
            return result

        declared = self._defs[token].supertypes
        if not transitive:
            result.update(declared)
            return result

        visited: set[str] = set()
        stack = list(declared)
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            result.add(current)
            if current in self._defs:
                stack.extend(self._defs[current].supertypes)

        return result

    def subtypes_of(self, token: str, *, transitive: bool = True) -> set[str]:
        """Return the subtype tokens of *token* (the reverse relation).

        For ``TOP_TYPE`` this is every other registered token. The token itself
        is never included.

        This is O(n) registered tokens per call (each delegating to
        :meth:`supertypes_of`), which is fine at the catalog's intended scale (a
        handful to low hundreds of tokens). It is an in-memory convenience query,
        not the exported artifact ADR 0012 keeps non-quadratic.
        """
        if token == TOP_TYPE:
            return set(self._defs.keys()) - {TOP_TYPE}

        result: set[str] = set()
        for other in self._defs:
            if other == token:
                continue
            if token in self.supertypes_of(other, transitive=transitive):
                result.add(other)
        return result

    def is_subtype(self, sub: str, sup: str) -> bool:
        """Return ``True`` iff *sub* is a transitive, non-reflexive subtype of *sup*.

        ``is_subtype(x, x)`` is ``False``; ``sup == TOP_TYPE`` is ``True`` for any
        ``sub != TOP_TYPE``.

        This is a pure subtype-graph membership query, not the three-valued
        ``is_compatible`` of ADR 0011 (Epic 3 Story 3): an unregistered *sub* is
        still reported a subtype of ``"any"`` here, whereas compatibility against
        an unregistered token is the future UNKNOWN/warn case.
        """
        if sub == sup:
            return False
        if sup == TOP_TYPE:
            return sub != TOP_TYPE
        return sup in self.supertypes_of(sub, transitive=True)

    def to_dict(self) -> dict[str, object]:
        """Serialize the catalog and subtype relation to a JSON-native dict.

        The result has these keys, in order:

        - ``"types"``: list of all registered tokens, sorted alphabetically.
        - ``"top"``: the top-type constant (``TOP_TYPE``).
        - ``"subtypes"``: list of ``[subtype, supertype]`` pairs, sorted, for each
          explicitly declared supertype edge.

        Implicit edges to ``"any"`` are NOT emitted — only edges explicitly declared
        on ``TypeDef.supertypes``. The ``version``/``semantics`` wrapper that turns
        this into the full portable rules artifact is added later (Epic 3 Story 7).
        The output is fully sorted, hence deterministic, so it can feed golden tests.
        """
        types = sorted(self._defs)
        subtypes = []
        for token, type_def in self._defs.items():
            for supertype in type_def.supertypes:
                subtypes.append([token, supertype])
        return {
            "types": types,
            "top": TOP_TYPE,
            "subtypes": sorted(subtypes),
        }

    def discover(self, *, group: str = ENTRY_POINT_GROUP) -> list[str]:
        """Load and register every type token published under *group*.

        Out-of-core packages contribute type tokens by declaring an entry point in
        the ``emergentflow.types`` group (or an overridden *group*). Each entry point's
        :meth:`~importlib.metadata.EntryPoint.load` should return a :class:`TypeDef`
        instance, which is passed to :meth:`register`.

        Resilience contract
        -------------------
        A single broken entry point — whether ``load()`` raises, the loaded object is
        not a valid ``TypeDef``, or :meth:`register` rejects it (e.g. a conflicting
        duplicate or a cycle) — must NOT abort discovery of the remaining entry points.
        Each failure is recorded as a human-readable problem string; discovery continues
        and returns the full list at the end.

        Parameters
        ----------
        group:
            The entry-point group to scan. Defaults to :data:`ENTRY_POINT_GROUP`
            (``"emergentflow.types"``).

        Returns
        -------
        list[str]
            Human-readable problem descriptions for any entry point that failed to load
            or register. Empty when all entry points were processed successfully.
        """
        problems: list[str] = []
        eps = importlib.metadata.entry_points(group=group)
        for ep in eps:
            try:
                loaded = ep.load()
                self.register(loaded)
            except Exception as exc:
                problems.append(
                    f"Entry point {ep.name!r} ({ep.value!r}) failed: {type(exc).__name__}: {exc}"
                )
        return problems

    def __contains__(self, token: str) -> bool:
        """Return ``True`` if *token* is registered (enables ``token in reg``)."""
        return token in self._defs

    def __len__(self) -> int:
        """Return the number of registered types."""
        return len(self._defs)

    def __iter__(self):
        """Yield each registered :class:`TypeDef`, sorted by token."""
        for token in sorted(self._defs):
            yield self._defs[token]


#: The default :class:`TypeRegistry` singleton. In-tree type tokens register here
#: via :func:`register_type`; tests should create their own ``TypeRegistry()`` to
#: stay isolated from the shared default.
registry = TypeRegistry()


def register_type(typedef: TypeDef) -> TypeDef:
    """Register *typedef* in the default :data:`registry`."""
    return registry.register(typedef)


def discover_types(*, group: str = ENTRY_POINT_GROUP) -> list[str]:
    """Discover and register entry-point type tokens into the default :data:`registry`.

    Delegates to :meth:`TypeRegistry.discover` on the default singleton; returns the
    list of human-readable problem strings (empty on full success).
    """
    return registry.discover(group=group)
