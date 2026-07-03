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
