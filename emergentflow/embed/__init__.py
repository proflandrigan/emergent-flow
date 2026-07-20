"""
emergentflow.embed
~~~~~~~~~~~~~~~~~~~
Text embedding family: ``ef.embed.text()`` — unified entry point for embedding a text
column in a DataFrame, dispatching to either an API provider (via the injected
``LLMClient`` seam, ADR 0017) or a local sentence-transformers model.

The API path builds an ``EmbeddingRequest`` and delegates the single effectful step to
``client.embed(request)``. Unlike ``ef.llm.call()``, this function returns a bare
augmented DataFrame with no per-call metadata (cost, latency, token usage) attached --
consistent with other feature-transform nodes (e.g. ``ef.timeseries.ewma``) -- so cost
is never computed here. Spend governance for the API path happens at the client edge,
by wrapping the injected client in ``emergentflow.llm.budget.BudgetClient``, which
tracks embedding cost the same way it tracks completion cost.
The local path lazy-imports ``sentence-transformers`` (optional ``emergentflow[embed]``
extra) and runs the model in-process — no client injection, and so no cost, needed.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import public_op
from emergentflow.embed.errors import (
    EmbedError,
    MissingClientError,
    MissingOptionalDependencyError,
)
from emergentflow.llm.protocol import EmbeddingRequest, EmbeddingResponse, LLMClient

__all__ = [
    "EmbedError",
    "MissingClientError",
    "MissingOptionalDependencyError",
    "text",
]


def _embed_api(
    texts: list[str],
    *,
    provider: str,
    model: str,
    client: LLMClient,
    api_key_env: str | None,
    llm_connection: str | None,
) -> EmbeddingResponse:
    """API embedding path — delegates to ``client.embed()``."""
    request = EmbeddingRequest(
        provider=provider,
        model=model,
        texts=tuple(texts),
        api_key_env=api_key_env,
        llm_connection=llm_connection,
    )
    return client.embed(request)


def _embed_local(
    texts: list[str],
    *,
    local_model: str,
) -> tuple[list[list[float]], int]:
    """Local embedding path — uses sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as exc:
        raise MissingOptionalDependencyError("emergentflow[embed]") from exc

    encoder = SentenceTransformer(local_model)
    vectors = encoder.encode(texts, show_progress_bar=False)
    embeddings = [row.tolist() for row in vectors]
    dimensions = len(embeddings[0]) if embeddings else 0
    return embeddings, dimensions


@public_op(name="ef.embed.text")
def text(
    data: pd.DataFrame,
    column: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    client: LLMClient | None = None,
    local_model: str | None = None,
    output_column: str = "embedding",
    api_key_env: str | None = None,
    llm_connection: str | None = None,
    batch_size: int = 64,
) -> pd.DataFrame:
    """Embed the text in *column* of *data* and return an augmented DataFrame.

    Dispatches to one of two backends:

    - **API** (``provider`` + ``model`` + ``client``): builds an ``EmbeddingRequest``
      and delegates to ``client.embed()``.
    - **Local** (``local_model``): lazy-imports sentence-transformers and runs
      the model in-process.

    Exactly one backend must be specified: either (``provider`` + ``model``) for
    the API path, or ``local_model`` for the local path.

    Parameters
    ----------
    data:
        Input DataFrame.
    column:
        Name of the text column to embed.
    provider:
        Gateway provider key for the API path, e.g. ``"openai"``.
    model:
        Provider model id for the API path, e.g. ``"text-embedding-3-small"``.
    client:
        The injected client (API path). Must expose an ``embed`` method.
    local_model:
        Sentence-transformers model name for the local path,
        e.g. ``"all-MiniLM-L6-v2"``.
    output_column:
        Name of the column to add to the DataFrame. Default ``"embedding"``.
    api_key_env:
        Environment variable name for the API key (API path only).
    llm_connection:
        Registered LLM credential profile name (API path only).
    batch_size:
        Number of texts to embed per API call. Default 64.

    Returns
    -------
    pd.DataFrame
        A copy of *data* with *output_column* appended, containing a list of
        floats per row.

    Raises
    ------
    EmbedError
        If neither or both backends are specified.
    MissingClientError
        If the API path is selected but no client is injected.
    MissingOptionalDependencyError
        If the local path is selected but sentence-transformers is not installed.
    """
    use_api = provider is not None and model is not None
    use_local = local_model is not None

    if use_api and use_local:
        raise EmbedError(
            "Specify either (provider + model) for the API path or "
            "local_model for the local path, not both."
        )
    if not use_api and not use_local:
        raise EmbedError(
            "Specify either (provider + model) for the API path or local_model for the local path."
        )

    if column not in data.columns:
        raise EmbedError(f"Column {column!r} not found in DataFrame.")

    if batch_size <= 0:
        raise EmbedError(f"batch_size must be a positive integer, got {batch_size!r}.")

    texts = data[column].astype(str).tolist()
    result = data.copy()

    if use_local:
        embeddings, _ = _embed_local(texts, local_model=local_model)  # type: ignore[arg-type]
        result[output_column] = embeddings
        return result

    # API path
    if client is None:
        raise MissingClientError(
            "ef.embed.text (API path) requires an injected client; pass "
            "client=... to execute(graph, client=...) or to the compiled "
            "module's main(client=...)."
        )

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _embed_api(
            batch,
            provider=provider,  # type: ignore[arg-type]
            model=model,  # type: ignore[arg-type]
            client=client,
            api_key_env=api_key_env,
            llm_connection=llm_connection,
        )
        all_embeddings.extend(response.embeddings)

    result[output_column] = all_embeddings
    return result
