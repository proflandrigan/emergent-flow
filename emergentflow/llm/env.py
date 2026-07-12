"""
emergentflow.llm.env
~~~~~~~~~~~~~~~~~~~~
Provider -> API-key env-var-name resolution, shared by `emergentflow.llm.gateway.GatewayClient`
(which resolves the actual key at call time) and `emergentflow.llm.secrets` (Epic 9 Story 9's
pre-flight check, which only needs to know the env-var *name* to check for its presence before
a run starts -- it never reads a key value here).
"""

from __future__ import annotations

#: Provider -> conventional env-var name, used when a request/param set does not set
#: `api_key_env` explicitly. Extend as new providers are added.
DEFAULT_API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class MissingAPIKeyError(RuntimeError):
    """Raised when an API-key env-var name cannot be resolved, or (by callers that check
    `os.environ` themselves) when the resolved env var is unset.

    The message names the *env var*, never a key value -- there is none to leak here.
    """


def resolve_api_key_env_name(provider: str, api_key_env: str | None) -> str:
    """Return the env-var name to read *provider*'s API key from.

    If *api_key_env* is given, it wins outright. Otherwise falls back to
    `DEFAULT_API_KEY_ENV[provider]`.

    Raises
    ------
    MissingAPIKeyError
        If *api_key_env* is unset and *provider* has no conventional default.
    """
    if api_key_env:
        return api_key_env
    default = DEFAULT_API_KEY_ENV.get(provider)
    if default is None:
        raise MissingAPIKeyError(
            f"No api_key_env was set and provider {provider!r} has no conventional "
            f"default env-var name. Set api_key_env explicitly "
            f"(known defaults: {sorted(DEFAULT_API_KEY_ENV)})."
        )
    return default


def resolve_effective_api_key_env_name(
    provider: str, api_key_env: str | None, llm_connection: str | None = None
) -> str:
    """Like `resolve_api_key_env_name`, but additionally resolves *llm_connection* (a registered
    LLM credential profile name) by reading the local connection-profile store.

    This is an EFFECTFUL function (file I/O) — call it only from effectful contexts
    (`GatewayClient.complete()`, the pre-flight check in `emergentflow.llm.secrets`), never from
    `compile_to_code`/`execute` (ADR 0002 purity).

    Precedence: if *llm_connection* is given, it wins — looked up in the local connection-profile
    store, returning its `api_key_env` field. Otherwise falls back to
    `resolve_api_key_env_name(provider, api_key_env)` (the existing pure raw-name/default path).

    Raises
    ------
    MissingAPIKeyError
        If *llm_connection* is given but no profile with that name is registered, or a profile
        with that name exists but is not an LLM-kind profile. Also raised (via the pure fallback)
        if neither *llm_connection* nor *api_key_env* is given and *provider* has no conventional
        default.
    """
    if llm_connection:
        from emergentflow.connections.profiles import (
            LlmConnectionProfile,
            UnknownConnectionError,
            load_profiles,
        )

        store = load_profiles()
        try:
            profile = store.get(llm_connection)
        except UnknownConnectionError as exc:
            raise MissingAPIKeyError(
                f"No LLM connection profile named {llm_connection!r} is registered. Configure "
                f"it via the canvas's Manage Connections panel (LLM Credentials section), or "
                f"clear this node's llm_connection param to use a raw env var instead."
            ) from exc
        if not isinstance(profile, LlmConnectionProfile):
            raise MissingAPIKeyError(
                f"Connection profile {llm_connection!r} is not an LLM credential profile "
                f"(found kind={profile.kind!r})."
            )
        return profile.api_key_env
    return resolve_api_key_env_name(provider, api_key_env)
