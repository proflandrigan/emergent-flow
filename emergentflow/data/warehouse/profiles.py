"""
emergentflow.data.warehouse.profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The local, secret-free connection-profile store (Epic 13 Story 3, ADR 0018).

A ``ConnectionProfile`` is a named, serializable descriptor of *how to reach* a
warehouse — its dialect, connection coordinates, auth *method*, and credential
*references* (env-var names / a keyring handle / a file path) — but **never a
credential value**. The IR references a profile by ``name`` only; the effectful
``WarehouseClient`` (Task 07) resolves the references to live credentials from
the environment / keyring at ``run()`` time. Because no secret value is ever a
field on this model, serializing a profile (or the whole store) cannot leak one.

The store is a plain local file (``~/.config/emergentflow/connections.toml`` by
default) loaded into an in-memory registry the SDK/server look up by name.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from sqlglot.dialects.dialect import Dialect


class ProfileError(ValueError):
    """Base class for connection-profile errors."""


class UnknownConnectionError(ProfileError):
    """Raised when a profile name is not present in the store."""


class ProfileValidationError(ProfileError):
    """Raised when a profile fails validation (bad dialect, missing coordinates)."""


def default_connections_path() -> Path:
    """Return the default local connections file path.

    Honors ``EMERGENTFLOW_CONNECTIONS`` if set, else
    ``~/.config/emergentflow/connections.toml``. This is a *local* path; the file
    it points at is never part of the IR (ADR 0018).
    """
    override = os.environ.get("EMERGENTFLOW_CONNECTIONS")
    if override:
        return Path(override)
    return Path.home() / ".config" / "emergentflow" / "connections.toml"


class ConnectionProfile(BaseModel):
    """A named, secret-free descriptor of how to reach one warehouse (ADR 0018).

    Fields
    ------
    name: profile name the IR references (e.g. ``"warehouse_prod"``).
    dialect: sqlglot dialect key (``"duckdb"``/``"bigquery"``/``"redshift"``/``"postgres"``).
    coordinates: non-secret connection coordinates (host, port, database, project,
        dataset, location, region, path, ...). Strings only; live locally, never in the IR.
    auth_method: how the client authenticates, e.g. ``"none"`` (DuckDB), ``"adc"``,
        ``"password_env"``, ``"service_account_file"``, ``"keyring"``.
    credential_refs: references to where secrets live — env-var *names*, a keyring
        handle, or a file *path*. **Never a secret value.** Keyed by role
        (e.g. ``{"password_env": "PGPASSWORD"}``).
    limits: default query limits (e.g. ``{"max_rows": 100000, "byte_scan_cap": ...,
        "timeout_s": 60}``). Enforced at the client edge (Task 07 / Story 8).
    write_enabled: when True, the read-only allow-list is relaxed for this profile
        (ADR 0018 read-only-by-default). Defaults to False.
    """

    name: str
    dialect: str
    coordinates: dict[str, str] = Field(default_factory=dict)
    auth_method: str = "none"
    credential_refs: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, int] = Field(default_factory=dict)
    write_enabled: bool = False

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ConnectionProfile.name must be a non-empty string.")
        return v

    @field_validator("dialect")
    @classmethod
    def _dialect_known(cls, v: str) -> str:
        try:
            Dialect.get_or_raise(v)
        except ValueError as exc:
            raise ValueError(
                f"Unknown SQL dialect {v!r}; must be a sqlglot dialect key "
                "(e.g. 'duckdb', 'bigquery', 'redshift', 'postgres')."
            ) from exc
        return v


class ConnectionTestResult(BaseModel):
    """Result of a design-time ``test_connection`` probe (inspectable, no secrets)."""

    name: str
    ok: bool
    message: str


class ProfileStore:
    """An in-memory, name-keyed registry of ``ConnectionProfile``s (secret-free)."""

    def __init__(self, profiles: dict[str, ConnectionProfile] | None = None) -> None:
        self._profiles: dict[str, ConnectionProfile] = dict(profiles or {})

    def add(self, profile: ConnectionProfile) -> None:
        self._profiles[profile.name] = profile

    def get(self, name: str) -> ConnectionProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._profiles)) or "<none>"
            raise UnknownConnectionError(
                f"No connection profile named {name!r}. Known profiles: {known}."
            ) from exc

    def names(self) -> list[str]:
        return sorted(self._profiles)

    def __contains__(self, name: object) -> bool:
        return name in self._profiles


def load_profiles(path: str | os.PathLike[str] | None = None) -> ProfileStore:
    """Load connection profiles from a local TOML file into a ``ProfileStore``.

    Each top-level table is one profile whose table name is the profile ``name``:

    .. code-block:: toml

        [warehouse_prod]
        dialect = "postgres"
        auth_method = "password_env"
        [warehouse_prod.coordinates]
        host = "db.internal"
        port = "5432"
        database = "analytics"
        [warehouse_prod.credential_refs]
        password_env = "PGPASSWORD"
        [warehouse_prod.limits]
        max_rows = 100000

    A missing file yields an empty store (a fresh install has no connections yet).
    """
    file_path = Path(path) if path is not None else default_connections_path()
    if not file_path.exists():
        return ProfileStore()
    with file_path.open("rb") as fh:
        raw = tomllib.load(fh)
    store = ProfileStore()
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ProfileValidationError(
                f"Top-level entry {name!r} in {file_path} must be a table (a profile)."
            )
        store.add(ConnectionProfile(name=name, **body))
    return store


def test_connection(
    profile: ConnectionProfile, *, client: object | None = None
) -> ConnectionTestResult:
    """Design-time probe that a profile is usable (ADR 0018; server/UI-facing).

    Always performs structural validation (a valid ``ConnectionProfile`` already
    guarantees a known dialect and a non-empty name). When a *client* with a
    ``list_relations`` method is supplied, additionally attempts a lightweight
    introspection call to prove connectivity; the real effectful client is Task
    07 / Story 7, so this stays duck-typed. Returns an inspectable result; never
    raises for a connectivity failure (the failure is reported in ``message``).
    """
    if client is not None and hasattr(client, "list_relations"):
        try:
            client.list_relations(profile.name)
        except Exception as exc:  # noqa: BLE001 - report, don't raise, at design time
            return ConnectionTestResult(
                name=profile.name, ok=False, message=f"Connection probe failed: {exc}"
            )
    return ConnectionTestResult(
        name=profile.name,
        ok=True,
        message=f"Profile {profile.name!r} ({profile.dialect}) is valid.",
    )
