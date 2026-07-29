"""
emergentflow.clients
~~~~~~~~~~~~~~~~~~~~~
The injected-client bundle (ADR 0018): one extensible container for every
effectful-client seam a graph might need, resolved by capability kind.

ADR 0017 threaded a single ``client`` (the LLM client) through ``execute`` and
the compiled ``main()``. ADR 0018 adds a second effect (warehouse queries) and
anticipates more (a vector store, object storage), so instead of a growing list
of positional ``client=`` parameters we thread ONE ``Clients`` bundle exposing
named seams. A node declares which capabilities it needs as a set of
``ClientKind``; the executor resolves each from the bundle.

This module is intentionally tiny and import-light (no node/codegen imports) so
both the node contract and the codegen layer can depend on it without cycles.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any


class ClientKind(enum.Enum):
    """A kind of injected effectful client (a seam on the ``Clients`` bundle)."""

    LLM = "llm"
    WAREHOUSE = "warehouse"
    HTTP = "http"


@dataclasses.dataclass(frozen=True)
class Clients:
    """A bundle of injected effectful clients, resolved by ``ClientKind``.

    Every seam defaults to ``None`` so a graph that needs none passes an empty
    bundle (or ``None``, which callers treat as empty). Additive by design: a new
    effect type is a new field here, not a new parameter on ``execute``/``main``.

    Attributes
    ----------
    llm: the injected ``LLMClient`` (ADR 0017), or ``None``.
    warehouse: the injected ``WarehouseClient`` (ADR 0018), or ``None``.
    http: the injected ``HttpClient`` (Epic 16 Story 1), or ``None``.
    """

    llm: Any | None = None
    warehouse: Any | None = None
    http: Any | None = None

    def for_kind(self, kind: ClientKind) -> Any | None:
        """Return the client seam for *kind* (``None`` if not supplied)."""
        if kind is ClientKind.LLM:
            return self.llm
        if kind is ClientKind.WAREHOUSE:
            return self.warehouse
        if kind is ClientKind.HTTP:
            return self.http
        raise KeyError(f"Unknown client kind: {kind!r}")

    @classmethod
    def from_legacy_client(cls, client: Any | None) -> Clients:
        """Build a bundle from the legacy ``execute(graph, client=...)`` keyword.

        The legacy single ``client`` always meant *the LLM client* (ADR 0017), so
        it maps onto the ``llm`` seam. This is the back-compat shim ADR 0018
        clause 3 requires; Task 09 uses it so old call sites keep working.
        """
        return cls(llm=client)
