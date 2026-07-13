"""
emergentflow.connections.profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The local, secret-free connection-profile store shared by the warehouse (ADR 0018) and LLM
(ADR 0017) node families.

A profile is a named, serializable descriptor of *how to reach* something (a warehouse or an
LLM provider) — coordinates, an auth method, and credential *references* (env-var names) — but
**never a credential value**. The IR references a profile by ``name`` only; the effectful client
(``AdapterWarehouseClient`` / ``GatewayClient``) resolves the reference to a live credential from
the environment at call time. Because no secret value is ever a field on either profile model,
serializing a profile (or the whole store) cannot leak one.

The store is a plain local TOML file (``~/.config/emergentflow/connections.toml`` by default)
loaded into an in-memory registry the SDK/server look up by name. Each top-level TOML table is
one profile keyed by name; a ``kind`` field (``"warehouse"`` or ``"llm"``) discriminates which
profile shape it is. A table with no ``kind`` field is treated as ``"warehouse"`` for backward
compatibility with connections.toml files written before this module existed.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Annotated, Literal

import tomli_w
from pydantic import BaseModel, Field, TypeAdapter, field_validator
from sqlglot.dialects.dialect import Dialect


class ProfileError(ValueError):
    """Base class for connection-profile errors."""


class UnknownConnectionError(ProfileError):
    """Raised when a profile name is not present in the store."""


class ProfileValidationError(ProfileError):
    """Raised when a profile fails validation (bad dialect, missing fields, unknown kind)."""


def default_connections_path() -> Path:
    """Return the default local connections file path.

    Honors ``EMERGENTFLOW_CONNECTIONS`` if set, else
    ``~/.config/emergentflow/connections.toml``. This is a *local* path; the file it points at is
    never part of the IR (ADR 0018).
    """
    override = os.environ.get("EMERGENTFLOW_CONNECTIONS")
    if override:
        return Path(override)
    return Path.home() / ".config" / "emergentflow" / "connections.toml"


class WarehouseConnectionProfile(BaseModel):
    """A named, secret-free descriptor of how to reach one warehouse (ADR 0018).

    Fields
    ------
    name: profile name the IR references (e.g. ``"warehouse_prod"``).
    kind: discriminator; always ``"warehouse"`` for this model.
    dialect: sqlglot dialect key (``"duckdb"``/``"bigquery"``/``"redshift"``/``"postgres"``).
    coordinates: non-secret connection coordinates (host, port, database, project, dataset,
        location, region, path, ...). Strings only; live locally, never in the IR.
    auth_method: how the client authenticates, e.g. ``"none"`` (DuckDB), ``"adc"``,
        ``"password_env"``, ``"service_account_file"``, ``"keyring"``.
    credential_refs: references to where secrets live — env-var *names*, a keyring handle, or a
        file *path*. **Never a secret value.** Keyed by role (e.g.
        ``{"password_env": "PGPASSWORD"}``).
    limits: default query limits (e.g. ``{"max_rows": 100000, "byte_scan_cap": ...,
        "timeout_s": 60}``). Enforced at the client edge.
    write_enabled: when True, the read-only allow-list is relaxed for this profile (ADR 0018
        read-only-by-default). Defaults to False.
    """

    name: str
    kind: Literal["warehouse"] = "warehouse"
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
            raise ValueError("WarehouseConnectionProfile.name must be a non-empty string.")
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


class LlmConnectionProfile(BaseModel):
    """A named, secret-free descriptor of how to authenticate to an LLM provider (ADR 0017).

    Fields
    ------
    name: profile name the IR references (e.g. ``"my_openai_key"``).
    kind: discriminator; always ``"llm"`` for this model.
    provider: gateway provider key, e.g. ``"anthropic"``, ``"openai"``, ``"gemini"``. Free-form
        (not a closed enum) since the LiteLLM-backed gateway supports arbitrary provider keys.
    api_key_env: name of the environment variable holding the provider API key. **Never the key
        itself** (ADR 0017 secrets rule).
    base_url_env: optional name of an environment variable holding a custom base URL (for
        self-hosted models / proxy gateways). ``None`` means use the provider's default endpoint.
    default_model: optional convenience default model id for this profile (e.g.
        ``"claude-sonnet-5"``). Purely informational; a node's own ``model`` param always wins.
    """

    name: str
    kind: Literal["llm"] = "llm"
    provider: str
    api_key_env: str
    base_url_env: str | None = None
    default_model: str | None = None

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("LlmConnectionProfile.name must be a non-empty string.")
        return v

    @field_validator("provider")
    @classmethod
    def _provider_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("LlmConnectionProfile.provider must be a non-empty string.")
        return v

    @field_validator("api_key_env")
    @classmethod
    def _api_key_env_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("LlmConnectionProfile.api_key_env must be a non-empty string.")
        return v


ConnectionProfile = Annotated[
    WarehouseConnectionProfile | LlmConnectionProfile, Field(discriminator="kind")
]
_PROFILE_ADAPTER: TypeAdapter[WarehouseConnectionProfile | LlmConnectionProfile] = TypeAdapter(
    ConnectionProfile
)


class ConnectionTestResult(BaseModel):
    """Result of a design-time ``test_connection`` probe (inspectable, no secrets)."""

    name: str
    ok: bool
    message: str


class ProfileStore:
    """An in-memory, name-keyed registry of profiles (secret-free), warehouse or LLM."""

    def __init__(
        self,
        profiles: dict[str, WarehouseConnectionProfile | LlmConnectionProfile] | None = None,
    ) -> None:
        self._profiles: dict[str, WarehouseConnectionProfile | LlmConnectionProfile] = dict(
            profiles or {}
        )

    def add(self, profile: WarehouseConnectionProfile | LlmConnectionProfile) -> None:
        """Add *profile*, overwriting any existing profile of the same name (upsert)."""
        self._profiles[profile.name] = profile

    def get(self, name: str) -> WarehouseConnectionProfile | LlmConnectionProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._profiles)) or "<none>"
            raise UnknownConnectionError(
                f"No connection profile named {name!r}. Known profiles: {known}."
            ) from exc

    def remove(self, name: str) -> None:
        """Remove the profile named *name*.

        Raises
        ------
        UnknownConnectionError
            If no profile with that name exists.
        """
        if name not in self._profiles:
            known = ", ".join(sorted(self._profiles)) or "<none>"
            raise UnknownConnectionError(
                f"No connection profile named {name!r}. Known profiles: {known}."
            )
        del self._profiles[name]

    def names(self, kind: str | None = None) -> list[str]:
        """Sorted profile names, optionally filtered by *kind* (``"warehouse"``/``"llm"``)."""
        if kind is None:
            return sorted(self._profiles)
        return sorted(n for n, p in self._profiles.items() if p.kind == kind)

    def list(
        self, kind: str | None = None
    ) -> list[WarehouseConnectionProfile | LlmConnectionProfile]:
        """Return every profile, optionally filtered to *kind*, ordered by name."""
        profiles = (
            self._profiles.values()
            if kind is None
            else (p for p in self._profiles.values() if p.kind == kind)
        )
        return sorted(profiles, key=lambda p: p.name)

    def __contains__(self, name: object) -> bool:
        return name in self._profiles


def load_profiles(path: str | os.PathLike[str] | None = None) -> ProfileStore:
    """Load connection profiles from a local TOML file into a ``ProfileStore``.

    Each top-level table is one profile whose table name is the profile ``name``. A table with no
    ``kind`` field is treated as ``kind = "warehouse"`` (backward compatibility with files written
    before the ``kind`` discriminator existed).

    .. code-block:: toml

        [warehouse_prod]
        dialect = "postgres"
        auth_method = "password_env"
        [warehouse_prod.coordinates]
        host = "db.internal"
        [warehouse_prod.credential_refs]
        password_env = "PGPASSWORD"

        [my_openai_key]
        kind = "llm"
        provider = "openai"
        api_key_env = "OPENAI_API_KEY"

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
        payload = {"name": name, **body}
        payload.setdefault("kind", "warehouse")
        try:
            profile = _PROFILE_ADAPTER.validate_python(payload)
        except Exception as exc:  # noqa: BLE001 - re-raised as our own typed error below
            raise ProfileValidationError(
                f"Profile {name!r} in {file_path} failed validation: {exc}"
            ) from exc
        store.add(profile)
    return store


def save_profiles(store: ProfileStore, path: str | os.PathLike[str] | None = None) -> None:
    """Write every profile in *store* back to a local TOML file at *path*.

    Creates the parent directory if it does not exist. Each profile is written as one top-level
    table keyed by its ``name`` (the ``name`` field itself is NOT repeated inside the table body,
    matching ``load_profiles``'s reader, which supplies ``name`` from the table key).
    """
    file_path = Path(path) if path is not None else default_connections_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, dict[str, object]] = {}
    for profile in store.list():
        body = profile.model_dump(exclude={"name"}, exclude_none=True)
        document[profile.name] = body
    with file_path.open("wb") as fh:
        tomli_w.dump(document, fh)


def test_connection(
    profile: WarehouseConnectionProfile, *, client: object | None = None
) -> ConnectionTestResult:
    """Design-time probe that a warehouse profile is usable (ADR 0018; server/UI-facing).

    Always performs structural validation (a valid ``WarehouseConnectionProfile`` already
    guarantees a known dialect and a non-empty name). When a *client* with a ``list_relations``
    method is supplied, additionally attempts a lightweight introspection call to prove
    connectivity. Returns an inspectable result; never raises for a connectivity failure (the
    failure is reported in ``message``).
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
