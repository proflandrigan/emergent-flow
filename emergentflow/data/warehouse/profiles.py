"""
emergentflow.data.warehouse.profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Backward-compatible re-export of the warehouse-specific pieces of the shared connection-profile
store (ADR 0018). The actual model/store/persistence implementation lives in
``emergentflow.connections.profiles``, which also serves the LLM node family (ADR 0017).
``ConnectionProfile`` here is specifically an alias for ``WarehouseConnectionProfile`` — every
existing caller in this package only ever constructs/consumes warehouse profiles, so the alias
keeps their code unchanged.

Not re-exported here: ``LlmConnectionProfile`` and ``save_profiles`` (no warehouse-module caller
uses either — the server routes that need to write profiles of both kinds import directly from
``emergentflow.connections.profiles`` instead).
"""

from __future__ import annotations

import os

from emergentflow.connections.profiles import ConnectionTestResult as ConnectionTestResult
from emergentflow.connections.profiles import ProfileError as ProfileError
from emergentflow.connections.profiles import ProfileStore as _ProfileStore
from emergentflow.connections.profiles import ProfileValidationError as ProfileValidationError
from emergentflow.connections.profiles import UnknownConnectionError as UnknownConnectionError
from emergentflow.connections.profiles import WarehouseConnectionProfile as ConnectionProfile
from emergentflow.connections.profiles import default_connections_path as default_connections_path
from emergentflow.connections.profiles import test_connection as test_connection


class ProfileStore(_ProfileStore):
    """A connection-profile store narrowed to warehouse profiles only.

    Every profile-access method guarantees a ``ConnectionProfile``
    (``WarehouseConnectionProfile``), never an ``LlmConnectionProfile``, matching the contract
    every warehouse-module caller expects.
    Loaded via the shim's ``load_profiles``, which discards LLM profiles at read time; this class
    also guards ``get()`` at runtime so a stray LLM profile never reaches consumer code.
    """

    def get(self, name: str) -> ConnectionProfile:
        profile = super().get(name)
        if not isinstance(profile, ConnectionProfile):
            raise UnknownConnectionError(f"Profile {name!r} is not a warehouse connection profile.")
        return profile


def load_profiles(
    path: str | os.PathLike[str] | None = None,
) -> ProfileStore:
    """Load *warehouse* connection profiles from a local TOML file into a ``ProfileStore``.

    Wraps the shared ``load_profiles`` and returns a ``ProfileStore`` narrowed to warehouse-only
    profiles, discarding any LLM profiles that may coexist in the file (the old, warehouse-only
    module never saw them). A missing file yields an empty store.
    """
    from emergentflow.connections.profiles import load_profiles as _load_profiles

    raw = _load_profiles(path)
    store = ProfileStore()
    for profile in raw.list():
        if isinstance(profile, ConnectionProfile):
            store.add(profile)
    return store


__all__ = [
    "ConnectionProfile",
    "ConnectionTestResult",
    "ProfileError",
    "ProfileStore",
    "ProfileValidationError",
    "UnknownConnectionError",
    "default_connections_path",
    "load_profiles",
    "test_connection",
]
