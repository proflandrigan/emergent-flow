# Text Embeddings

Embed text columns in a DataFrame via API providers or local models.

## 1. Local Embeddings (sentence-transformers)

```python
import emergentflow as ef
import pandas as pd

df = pd.DataFrame({
    "id": [1, 2, 3],
    "text": ["Machine learning is great", "Data science rocks", "Neural networks are powerful"],
})

# Requires: pip install 'emergentflow[embed]'
result = ef.embed.text(df, "text", local_model="all-MiniLM-L6-v2")
print(result.columns.tolist())  # ['id', 'text', 'embedding']
print(len(result["embedding"].iloc[0]))  # 384 (dimensions for MiniLM)
print(result["embedding"].iloc[0][:5])   # [0.023, -0.041, ...]
```

`result` is a copy of `df` with an `embedding` column appended, holding a list of floats
per row.

## 2. API Embeddings

```python
from emergentflow.llm.gateway import GatewayClient

client = GatewayClient()

result = ef.embed.text(
    df, "text",
    provider="openai",
    model="text-embedding-3-small",
    client=client,
    api_key_env="OPENAI_API_KEY",
)
```

`api_key_env` is the env var *name*, not the key itself — credentials never enter the IR.
Can also use `llm_connection` for a named connection profile instead.

Exactly one backend must be specified: either (`provider` + `model`) for the API path, or
`local_model` for the local path — specifying both, or neither, raises `EmbedError`.

## 3. Custom Output Column

```python
result = ef.embed.text(df, "text", local_model="all-MiniLM-L6-v2", output_column="text_vector")
print(result.columns.tolist())  # ['id', 'text', 'text_vector']
```

## 4. Batch Size

```python
# Control batch size for API calls (default 64)
result = ef.embed.text(
    df, "text",
    provider="openai", model="text-embedding-3-small",
    client=client, batch_size=32,
)
```

## 5. Using Embeddings for Downstream Tasks

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

embeddings = np.array(result["embedding"].tolist())
similarities = cosine_similarity(embeddings)
print(similarities)
```

> **In the Canvas:** Add an `embed_text` node and connect a DataFrame source. Configure the
> embedding backend (local model name or API provider/model) in the Config tab. The output
> DataFrame flows to downstream nodes with the embedding column appended. See
> [Canvas UI Guide](canvas-ui-guide.md).
