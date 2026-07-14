"""
emergentflow.data.warehouse.credentials
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Credential resolution at the effect edge (Epic 13 Story 3, ADR 0018).

A ``ConnectionProfile`` (``emergentflow.data.warehouse.profiles``) carries only
credential *references* — env-var names (keys suffixed ``_env``), keyring
handles, or file paths — never secret values. ``resolve_credentials`` turns those
references into live values at ``run()`` time by reading ``os.environ`` (the one
edge-level effect, like ``GatewayClient``). It runs inside the effectful client
only; the pure core never imports it. A missing env var raises a typed error
naming the *variable*, never a value.
"""

from __future__ import annotations

import os

from emergentflow.data.warehouse.profiles import ConnectionProfile

IMPLICIT_AUTH_METHODS = frozenset({"adc", "implicit", "none"})
"""``auth_method`` values that carry no ``credential_refs`` — the platform resolves the
credential implicitly (BigQuery Application Default Credentials, Postgres peer/implicit
auth). Profiles using one of these methods have empty ``credential_refs`` by construction,
so ``resolve_credentials``/``required_env_vars`` already no-op correctly; this constant
documents the known set and lets the pre-flight module skip the env-var check explicitly."""


class MissingConnectionCredentialError(RuntimeError):
    """Raised when a profile's referenced credential env var is unset (names the var only)."""


def required_env_vars(profile: ConnectionProfile) -> list[str]:
    """Return the env-var NAMES a profile references (``credential_refs`` keys ending ``_env``).

    These are names, not values — safe to log or surface. Used by the pre-flight
    check and by ``resolve_credentials``.
    """
    return [ref for role, ref in profile.credential_refs.items() if role.endswith("_env")]


def resolve_credentials(profile: ConnectionProfile) -> dict[str, str]:
    """Resolve a profile's credential references to live values (edge-only effect).

    - ``credential_refs`` keys suffixed ``_env`` resolve from ``os.environ``; the
      resolved value is stored under the key with the suffix stripped (e.g.
      ``{"password_env": "PGPASSWORD"}`` -> ``{"password": <value>}``).
    - other refs (keyring handles, file paths, an ADC marker) pass through
      unchanged under their original key — the adapter interprets them.

    Raises
    ------
    MissingConnectionCredentialError
        If a referenced env var is not set (names the variable, never a value).
    """
    resolved: dict[str, str] = {}
    for role, ref in profile.credential_refs.items():
        if role.endswith("_env"):
            value = os.environ.get(ref)
            if not value:
                raise MissingConnectionCredentialError(
                    f"Connection profile {profile.name!r} needs the {ref!r} environment "
                    f"variable, which is not set. Export it before running this graph, e.g.:\n"
                    f"    export {ref}=<value>"
                )
            resolved[role[: -len("_env")]] = value
        else:
            resolved[role] = ref
    return resolved
