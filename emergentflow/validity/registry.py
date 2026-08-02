"""
emergentflow.validity.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Validity rule registry (Epic 17, Story 2).

Mirrors ``emergentflow.nodes.registry``: a registry holding every registered
:class:`~emergentflow.validity.contract.ValidityRule` subclass, a module-level
singleton, and a ``@validity_rule`` class decorator. Registration is fail-fast
(duplicate id, missing metadata, bad severity/confidence all raise
``ValueError``).
"""

from __future__ import annotations

from .contract import CONFIDENCE, SEVERITIES, ValidityRule

#: Version of the rule-pack artifact emitted from the default registry.
#: Bump when a rule's metadata (id, severity, title, rationale) changes in a
#: way the canvas must see.
PACK_VERSION: int = 2


class ValidityRuleRegistry:
    """Registry of :class:`ValidityRule` subclasses.

    Rules self-register via the module-level :func:`validity_rule` decorator
    (or :meth:`register` directly). Importing ``emergentflow.validity`` fires
    registration of every in-tree rule.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._rules: dict[str, type[ValidityRule]] = {}

    def register(self, rule: type[ValidityRule]) -> type[ValidityRule]:
        """Register *rule* and return it unchanged (usable as a class decorator).

        Raises ``ValueError`` on violation:
        1. *rule* must be a proper subclass of ``ValidityRule`` (not the
           abstract base itself, not a non-class object).
        2. ``id``, ``title``, and ``rationale`` must be non-empty strings.
        3. ``severity`` must be one of ``SEVERITIES``.
        4. ``confidence`` must be one of ``CONFIDENCE``.
        5. Duplicate id: registering a *different* class under an already-used
           ``id`` raises ``ValueError``; registering the *same* class object a
           second time is a harmless no-op.
        """
        # --- check 1: must be a proper subclass of ValidityRule -----------
        if not isinstance(rule, type) or not issubclass(rule, ValidityRule):
            raise ValueError(
                f"{rule!r} is not a subclass of ValidityRule; "
                "only ValidityRule subclasses may be registered."
            )
        if rule is ValidityRule:
            raise ValueError(
                "Cannot register the abstract ValidityRule base class itself; "
                "register a concrete subclass instead."
            )

        # --- check 2: id, title, rationale must be non-empty strings ------
        for attr in ("id", "title", "rationale"):
            try:
                value = getattr(rule, attr)
            except AttributeError:
                raise ValueError(
                    f"{rule.__name__!r} has no {attr!r} class attribute set; "
                    "every ValidityRule subclass must declare it."
                ) from None
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{rule.__name__!r} has an empty or non-string {attr!r} "
                    f"attribute ({value!r}); it must be a non-empty string."
                )

        # --- check 3: severity must be one of SEVERITIES ------------------
        if rule.severity not in SEVERITIES:
            raise ValueError(
                f"{rule.__name__!r} declares severity {rule.severity!r}; "
                f"expected one of {SEVERITIES!r}."
            )

        # --- check 4: confidence must be one of CONFIDENCE ----------------
        if rule.confidence not in CONFIDENCE:
            raise ValueError(
                f"{rule.__name__!r} declares confidence {rule.confidence!r}; "
                f"expected one of {CONFIDENCE!r}."
            )

        # --- check 5: duplicate-id guard ----------------------------------
        existing = self._rules.get(rule.id)
        if existing is not None:
            if existing is rule:
                # Idempotent re-registration of the same class -- silently allow.
                return rule
            raise ValueError(
                f"Cannot register {rule.__name__!r} under id {rule.id!r}: "
                f"that id is already registered to {existing.__name__!r}. "
                "Use a unique 'id' for each validity rule."
            )

        self._rules[rule.id] = rule
        return rule

    def get(self, rule_id: str) -> type[ValidityRule]:
        """Return the rule registered under *rule_id*.

        Raises ``KeyError`` if *rule_id* is not registered.
        """
        try:
            return self._rules[rule_id]
        except KeyError:
            raise KeyError(f"{rule_id!r} is not registered in this ValidityRuleRegistry.") from None

    def try_get(self, rule_id: str) -> type[ValidityRule] | None:
        """Non-raising variant of :meth:`get`."""
        return self._rules.get(rule_id)

    def all(self) -> list[type[ValidityRule]]:
        """Return every registered rule, sorted by id (deterministic)."""
        return sorted(self._rules.values(), key=lambda r: r.id)

    def specs(self) -> list[dict[str, str]]:
        """Return the serializable rule-pack view for the artifact builder.

        One dict per rule, in the same sorted order as :meth:`all`. Dict keys:
        ``id``, ``severity``, ``confidence``, ``title``, ``rationale``. These
        must remain JSON-serializable (they feed ``schema/validity-rules.json``).
        """
        return [
            {
                "id": rule.id,
                "severity": rule.severity,
                "confidence": rule.confidence,
                "title": rule.title,
                "rationale": rule.rationale,
            }
            for rule in self.all()
        ]

    def __iter__(self):
        """Yield every registered rule in sorted order."""
        yield from self.all()

    def __contains__(self, rule_id: str) -> bool:
        """``True`` if *rule_id* is registered."""
        return rule_id in self._rules

    def __len__(self) -> int:
        """Return the number of currently registered rules."""
        return len(self._rules)


#: The default :class:`ValidityRuleRegistry` singleton. In-tree rules register
#: here via the module-level :func:`validity_rule` decorator.
registry = ValidityRuleRegistry()


def validity_rule(rule: type[ValidityRule]) -> type[ValidityRule]:
    """Register *rule* in the default :data:`registry`.

    Usable as a bare class decorator::

        from emergentflow.validity import validity_rule

        @validity_rule
        class FitBeforeSplit(ValidityRule):
            id = "fit_before_split"
            severity = "error"
            confidence = "high"
            title = "..."
            rationale = "..."
            def check(self, graph):
                ...

    Delegates entirely to :meth:`ValidityRuleRegistry.register` on the default
    singleton.
    """
    return registry.register(rule)
