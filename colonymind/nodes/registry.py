"""
colonymind.nodes.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~
The node-definition registry (Epic 1, Story 4).

The registry indexes :class:`~colonymind.nodes.contract.NodeDefinition` subclasses
by their ``type`` class attribute, giving the rest of the system a single,
authoritative catalog of every known node type.

In-tree node definitions register against the module-level default ``registry``
singleton using the :func:`register` decorator::

    from colonymind.nodes.registry import register

    @register
    class MyNode(NodeDefinition):
        type = "my.node"
        ...

Out-of-core nodes (third-party plugins) are discovered automatically via Python
package entry points — see ``discover()`` (Task 04).

Lookups return the definition *classes* themselves, not instances.  This is a
deliberate design decision: the caller instantiates as needed, and the registry
stays lightweight (it holds no live objects, only class references).
"""

from __future__ import annotations

import importlib.metadata

from colonymind.ir.common import Direction
from colonymind.nodes.contract import NodeDefinition
from colonymind.nodes.spec import NodeSpec

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The entry-point group third-party packages publish node definitions under.
ENTRY_POINT_GROUP = "colonymind.nodes"

# ---------------------------------------------------------------------------
# NodeRegistry
# ---------------------------------------------------------------------------


class NodeRegistry:
    """An indexed catalog of :class:`~colonymind.nodes.contract.NodeDefinition`
    subclasses.

    Each definition is stored under its ``type`` catalog key.  The registry
    is a plain class (not a Pydantic model) because it holds live Python
    classes, not serializable data.

    Typical usage
    -------------
    Use the module-level :data:`registry` singleton and the :func:`register`
    decorator for in-tree nodes.  Create a fresh ``NodeRegistry()`` in tests
    so tests are isolated from the shared default.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._defs: dict[str, type[NodeDefinition]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, definition: type[NodeDefinition]) -> type[NodeDefinition]:
        """Register *definition* and return it unchanged.

        The return value means this method doubles as a class decorator::

            @registry.register
            class MyNode(NodeDefinition):
                type = "my.node"
                ...

        Fail-fast checks (each raises :class:`ValueError` on violation):

        1. *definition* must be a proper subclass of ``NodeDefinition`` — not
           the abstract base itself, and not a non-class object.
        2. The ``type``, ``family``, and ``label`` class attributes must be
           present and non-empty strings.  (``NodeDefinition.type`` is an
           unannotated ``ClassVar``; a subclass that forgets to set it raises
           ``AttributeError`` on access, which is caught and reported as a
           ``ValueError``.)
        3. ``definition().to_spec()`` must succeed — this validates the full
           ``NodeSpec`` via Pydantic and proves the definition is concrete and
           well-formed.
        4. Duplicate key: registering a *different* class under an already-
           registered ``type`` raises ``ValueError``.  Registering the *same*
           class object a second time is a harmless no-op (idempotent).

        Parameters
        ----------
        definition:
            The ``NodeDefinition`` subclass to register.

        Returns
        -------
        type[NodeDefinition]
            The same *definition* class, unchanged.

        Raises
        ------
        ValueError
            For any of the fail-fast checks described above.
        """
        # --- check 1: must be a proper subclass of NodeDefinition ----------
        if not isinstance(definition, type) or not issubclass(definition, NodeDefinition):
            raise ValueError(
                f"{definition!r} is not a subclass of NodeDefinition; "
                "only NodeDefinition subclasses may be registered."
            )
        if definition is NodeDefinition:
            raise ValueError(
                "Cannot register the abstract NodeDefinition base class itself; "
                "register a concrete subclass instead."
            )

        # --- check 2: type, family, label must be present and non-empty ----
        for attr in ("type", "family", "label"):
            try:
                value = getattr(definition, attr)
            except AttributeError:
                raise ValueError(
                    f"{definition.__name__!r} has no {attr!r} class attribute set; "
                    f"every NodeDefinition subclass must declare {attr!r}."
                ) from None
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{definition.__name__!r} has an empty or non-string {attr!r} "
                    f"attribute ({value!r}); it must be a non-empty string."
                )

        # After check 2 we know definition.type is a valid, non-empty string.
        type_key: str = definition.type

        # --- check 3: definition().to_spec() must succeed -------------------
        try:
            definition().to_spec()
        except Exception as exc:
            raise ValueError(
                f"Registering {type_key!r}: definition().to_spec() raised "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        # --- check 4: duplicate-key guard -----------------------------------
        existing = self._defs.get(type_key)
        if existing is not None:
            if existing is definition:
                # Idempotent re-registration of the same class — silently allow.
                return definition
            raise ValueError(
                f"Cannot register {definition.__name__!r} under {type_key!r}: "
                f"that key is already registered to {existing.__name__!r}. "
                "Use a unique 'type' value for each node definition."
            )

        self._defs[type_key] = definition
        return definition

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get(self, type_key: str) -> type[NodeDefinition]:
        """Return the definition registered under *type_key*.

        Parameters
        ----------
        type_key:
            The catalog key to look up.

        Returns
        -------
        type[NodeDefinition]
            The registered definition class.

        Raises
        ------
        KeyError
            If *type_key* is not registered.
        """
        try:
            return self._defs[type_key]
        except KeyError:
            raise KeyError(f"{type_key!r} is not registered in this NodeRegistry.") from None

    def try_get(self, type_key: str) -> type[NodeDefinition] | None:
        """Return the definition registered under *type_key*, or ``None``.

        Non-raising variant of :meth:`get`.

        Parameters
        ----------
        type_key:
            The catalog key to look up.

        Returns
        -------
        type[NodeDefinition] or None
            The registered definition class, or ``None`` if absent.
        """
        return self._defs.get(type_key)

    def by_family(self, family: str) -> list[type[NodeDefinition]]:
        """Return all definitions belonging to *family*, sorted by type.

        Parameters
        ----------
        family:
            The family string to filter by (exact match).

        Returns
        -------
        list[type[NodeDefinition]]
            Definitions whose ``family`` equals *family*, sorted by ``type``.
            Returns an empty list if none match.
        """
        return sorted(
            (d for d in self._defs.values() if d.family == family),
            key=lambda d: d.type,
        )

    def by_port_type(
        self,
        data_type: str,
        direction: Direction | None = None,
    ) -> list[type[NodeDefinition]]:
        """Return all definitions declaring at least one port with *data_type*.

        Parameters
        ----------
        data_type:
            The port data-type token to search for (e.g. ``"Table"``).
        direction:
            When given, only ports of this direction are considered.  When
            ``None``, ports of either direction are matched.

        Returns
        -------
        list[type[NodeDefinition]]
            Definitions that have a matching port, sorted by ``type``.
            Returns an empty list if none match.
        """
        results = []
        for d in self._defs.values():
            for ps in d.ports:
                if ps.data_type == data_type and (direction is None or ps.direction == direction):
                    results.append(d)
                    break
        return sorted(results, key=lambda d: d.type)

    def all(self) -> list[type[NodeDefinition]]:
        """Return every registered definition, sorted by type.

        Returns
        -------
        list[type[NodeDefinition]]
            All registered definitions sorted by ``type``.
        """
        return sorted(self._defs.values(), key=lambda d: d.type)

    def specs(self) -> list[NodeSpec]:
        """Return the serializable catalog view for the UI.

        Calls ``to_spec()`` on a fresh instance of each definition, in the
        same sorted order as :meth:`all`.

        Returns
        -------
        list[NodeSpec]
            One :class:`~colonymind.nodes.spec.NodeSpec` per registered
            definition, sorted by ``type``.
        """
        return [d().to_spec() for d in self.all()]

    def validate(self) -> list[str]:
        """Audit every registered definition and return all problems found.

        Returns a (possibly empty) list of human-readable problem messages
        collected across the entire catalog.  The registry may have been
        populated entirely via :meth:`register` (which performs its own
        fail-fast checks) or partially via direct ``_defs`` assignment (e.g.
        to simulate corruption in tests).  This sweep exists to catch:

          * deeper invariants ``register`` does not check (port-name
            uniqueness per direction, param-name uniqueness);
          * bypass corruption — a class inserted under the wrong key;
          * post-registration mutation (``to_spec()`` can be checked again
            cheaply).

        Checks per definition
        ---------------------
        1. **Stored key matches declared type** — the dict key must equal
           ``definition.type``.
        2. **``to_spec()`` succeeds** — the full Pydantic spec round-trip must
           not raise.
        3. **Port name uniqueness per direction** — within one definition, no
           two ports sharing the same direction may also share a name.  Two
           ports of *different* directions sharing a name is explicitly legal.
        4. **Param name uniqueness** — within one definition, no two params
           may share a name.
        5. **version is an int >= 1.**

        Returns
        -------
        list[str]
            Sorted list of problem descriptions; empty when the catalog is
            healthy.
        """
        errors: list[str] = []

        for stored_key, definition in self._defs.items():
            # ---- check 1: stored key must match definition.type ----
            try:
                declared_type = definition.type
            except AttributeError:
                errors.append(f"Definition stored under {stored_key!r} has no 'type' attribute.")
                continue

            if stored_key != declared_type:
                errors.append(
                    f"Key mismatch: definition is stored under {stored_key!r} but "
                    f"declares type={declared_type!r}."
                )

            # ---- check 2: to_spec() must succeed ----
            try:
                definition().to_spec()
            except Exception as exc:
                errors.append(f"{declared_type!r}: to_spec() raised {type(exc).__name__}: {exc}")

            # ---- check 3: port name uniqueness per direction ----
            try:
                ports = definition.ports
            except AttributeError:
                ports = []

            seen_ports: dict[tuple, int] = {}
            for ps in ports:
                key = (ps.direction, ps.name)
                seen_ports[key] = seen_ports.get(key, 0) + 1

            for (direction, name), count in seen_ports.items():
                if count > 1:
                    errors.append(
                        f"{declared_type!r}: duplicate {direction.value.upper()} port "
                        f"name {name!r} ({count} occurrences)."
                    )

            # ---- check 4: param name uniqueness ----
            try:
                params = definition.params
            except AttributeError:
                params = []

            seen_params: dict[str, int] = {}
            for param in params:
                seen_params[param.name] = seen_params.get(param.name, 0) + 1

            for name, count in seen_params.items():
                if count > 1:
                    errors.append(
                        f"{declared_type!r}: duplicate param name {name!r} ({count} occurrences)."
                    )

            # ---- check 5: version is an int >= 1 ----
            try:
                version = definition.version
            except AttributeError:
                errors.append(f"{declared_type!r}: missing 'version' attribute.")
            else:
                if not isinstance(version, int) or isinstance(version, bool):
                    errors.append(
                        f"{declared_type!r}: version must be an int >= 1; got {version!r}."
                    )
                elif version < 1:
                    errors.append(f"{declared_type!r}: version must be >= 1; got {version!r}.")

        return sorted(errors)

    def discover(self, *, group: str = ENTRY_POINT_GROUP) -> list[str]:
        """Load and register every entry point published under *group*.

        Third-party packages contribute node definitions by declaring an entry
        point in the ``colonymind.nodes`` group (or an overridden *group*).
        Each entry point's :meth:`~importlib.metadata.EntryPoint.load` should
        return a :class:`~colonymind.nodes.contract.NodeDefinition` subclass;
        it is then passed to :meth:`register`.

        Resilience contract
        -------------------
        A single broken entry point — whether ``load()`` raises, the loaded
        object is not a valid ``NodeDefinition`` subclass, or :meth:`register`
        rejects it (e.g. duplicate key) — must **not** abort discovery of the
        remaining entry points.  Each failure is recorded as a human-readable
        problem string; discovery continues and returns the full list at the end.

        Calling ``discover()`` when some (or all) plugins are already registered
        is safe: :meth:`register` is idempotent for the same class object, and
        a *conflicting* duplicate becomes a recorded problem.

        Parameters
        ----------
        group:
            The entry-point group to scan.  Defaults to
            :data:`ENTRY_POINT_GROUP` (``"colonymind.nodes"``).

        Returns
        -------
        list[str]
            Human-readable problem descriptions for any entry point that failed
            to load or register.  Empty when all entry points were processed
            successfully.  Successful registrations are observable via the
            registry itself (``len``, :meth:`get`, ``in``, …).
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

    # ------------------------------------------------------------------
    # Dunder helpers for ergonomics / testing
    # ------------------------------------------------------------------

    def __iter__(self):
        """Yield every registered definition in sorted order.

        Allows ``for d in registry`` syntax; equivalent to iterating over
        :meth:`all`.
        """
        yield from self.all()

    def __contains__(self, type_key: str) -> bool:
        """Return ``True`` if *type_key* is registered in this registry.

        Allows ``"my.node" in registry`` syntax.
        """
        return type_key in self._defs

    def __len__(self) -> int:
        """Return the number of definitions currently registered."""
        return len(self._defs)


# ---------------------------------------------------------------------------
# Module-level default singleton and convenience decorator
# ---------------------------------------------------------------------------

#: The default :class:`NodeRegistry` singleton.  In-tree node definitions
#: register here via the module-level :func:`register` decorator.  Tests
#: should create their own ``NodeRegistry()`` to remain isolated.
registry = NodeRegistry()


def register(definition: type[NodeDefinition]) -> type[NodeDefinition]:
    """Register *definition* in the default :data:`registry`.

    Usable as a bare class decorator::

        from colonymind.nodes.registry import register

        @register
        class MyNode(NodeDefinition):
            type = "my.node"
            family = "my"
            label = "My Node"
            ...

    Delegates entirely to :meth:`NodeRegistry.register` on the default
    singleton; see that method for the full list of checks and error messages.

    Parameters
    ----------
    definition:
        The ``NodeDefinition`` subclass to register.

    Returns
    -------
    type[NodeDefinition]
        The same *definition* class, unchanged.
    """
    return registry.register(definition)


def get(type_key: str) -> type[NodeDefinition]:
    """Look up *type_key* in the default :data:`registry`.

    Delegates to :meth:`NodeRegistry.get` on the default singleton.

    Parameters
    ----------
    type_key:
        The catalog key to look up.

    Returns
    -------
    type[NodeDefinition]
        The registered definition class.

    Raises
    ------
    KeyError
        If *type_key* is not registered in the default registry.
    """
    return registry.get(type_key)


def by_family(family: str) -> list[type[NodeDefinition]]:
    """Return all definitions in *family* from the default :data:`registry`.

    Delegates to :meth:`NodeRegistry.by_family` on the default singleton.

    Parameters
    ----------
    family:
        The family string to filter by (exact match).

    Returns
    -------
    list[type[NodeDefinition]]
        Definitions sorted by ``type``; empty list if none match.
    """
    return registry.by_family(family)


def by_port_type(
    data_type: str,
    direction: Direction | None = None,
) -> list[type[NodeDefinition]]:
    """Return all definitions with a port of *data_type* from the default :data:`registry`.

    Delegates to :meth:`NodeRegistry.by_port_type` on the default singleton.

    Parameters
    ----------
    data_type:
        The port data-type token to search for.
    direction:
        When given, only ports of this direction are considered.

    Returns
    -------
    list[type[NodeDefinition]]
        Definitions sorted by ``type``; empty list if none match.
    """
    return registry.by_port_type(data_type, direction)


def validate() -> list[str]:
    """Audit the default :data:`registry` and return all problems found.

    Delegates to :meth:`NodeRegistry.validate` on the default singleton.
    Returns a (possibly empty) sorted list of human-readable problem messages
    across the entire catalog; raises nothing for a bad catalog.

    Returns
    -------
    list[str]
        Sorted list of problem descriptions; empty when the catalog is healthy.
    """
    return registry.validate()


def discover(*, group: str = ENTRY_POINT_GROUP) -> list[str]:
    """Discover and register entry points from *group* in the default :data:`registry`.

    Delegates to :meth:`NodeRegistry.discover` on the default singleton.
    Loads every entry point published under *group* and registers the resulting
    :class:`~colonymind.nodes.contract.NodeDefinition` subclasses.  Broken
    entry points are collected as problem strings rather than raised.

    Parameters
    ----------
    group:
        The entry-point group to scan.  Defaults to
        :data:`ENTRY_POINT_GROUP` (``"colonymind.nodes"``).

    Returns
    -------
    list[str]
        Human-readable problem descriptions for any entry point that failed
        to load or register.  Empty when all entry points were processed
        successfully.
    """
    return registry.discover(group=group)
