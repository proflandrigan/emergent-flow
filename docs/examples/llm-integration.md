# LLM Integration

Emergent Flow calls LLMs through an injected client — never a hardcoded API call. Prompt
template rendering is pure; the network call is the only effectful step, and it happens
entirely inside the client you inject (`GatewayClient` for a real provider, `ReplayClient` for
fixture replay in tests). This guide walks through templating, calling, structured output,
connection profiles, eval runs (the Prompt Lab), labeling/export, and how client injection
flows through both `execute()` and compiled code.

## 1. Prompt Templates

`ef.llm.prompt` renders a system/user template pair against a variable-binding dict into a
`PromptSpec`. Templating is constrained to `{{var}}` substitution only — no arbitrary code
execution, no I/O:

```python
import emergentflow as ef

spec = ef.llm.prompt(
    system="You are a helpful data analyst.",
    user="Summarize this dataset: {{description}}",
    variables={"description": "150 rows of iris flower measurements with 4 features and a species label"},
)
print(spec.system)   # "You are a helpful data analyst."
print(spec.user)     # "Summarize this dataset: 150 rows of iris flower measurements..."
print(spec.messages) # ({"role": "system", "content": "..."}, {"role": "user", "content": "..."})
```

`spec.messages` is a tuple of `{"role": ..., "content": ...}` dicts, ready to hand straight to
`ef.llm.call`. `ef.llm.prompt` raises `PromptVariableError` if a template references a variable
missing from `variables`, or if `variables` supplies a key neither template references.

## 2. Making LLM Calls

`ef.llm.call` takes the rendered `messages`, a `provider`/`model` pair, and an injected
`client`, and returns an `LLMResponse`:

```python
from emergentflow.llm.gateway import GatewayClient

client = GatewayClient()

response = ef.llm.call(
    spec.messages,
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    client=client,
    api_key_env="ANTHROPIC_API_KEY",
)
print(response.text)          # The LLM's response text ("response_format='text'", the default)
print(response.model)         # "claude-sonnet-4-20250514"
print(response.usage.input_tokens, response.usage.output_tokens)   # 42 128
print(f"Cost: ${response.cost_usd:.4f}")
print(f"Latency: {response.latency_ms:.0f}ms")
```

`api_key_env` is the *name* of the environment variable holding the API key (e.g.
`"ANTHROPIC_API_KEY"`), never the key itself — credentials never enter the graph IR.
`GatewayClient` resolves the real key from `os.environ` at call time, raising
`MissingAPIKeyError` if it isn't set. `client` is required: passing `client=None` (or omitting
it against a node with no injected client) raises `MissingClientError`.

`cost_usd` is always (re)computed by `ef.llm.call` itself from `response.model` and
`response.usage` against a central price table — neither `GatewayClient` nor `ReplayClient`
computes its own cost.

## 3. Structured Output (JSON)

Set `response_format="json"` to have `ef.llm.call` parse the response as JSON into
`response.data`, and pass `response_schema` (a JSON Schema) to validate the parsed result:

```python
response = ef.llm.call(
    [{"role": "user", "content": "List the top 3 features of the iris dataset as JSON."}],
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    client=client,
    response_format="json",
    response_schema={
        "type": "object",
        "required": ["features"],
        "properties": {
            "features": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
    },
)
print(response.data)  # {"features": ["sepal length", "sepal width", ...]}
print(response.text)  # None -- text is only populated for response_format="text"
```

`response_schema` validates a constrained structural subset of JSON Schema (`type`,
`properties`, `required`, `items` — no external JSON-Schema library dependency). A mismatch
raises `StructuredOutputValidationError` listing every violation found.

## 4. Connection Profiles

Instead of naming an env var directly with `api_key_env`, you can reference a named connection
profile via `llm_connection`:

```python
response = ef.llm.call(
    messages,
    provider="openai",
    model="gpt-4o",
    client=client,
    llm_connection="my_openai_profile",
)
```

Connection profiles are configured in `~/.config/emergentflow/connections.toml` and, like
`api_key_env`, carry only an env-var *name* — never a credential value. `GatewayClient`
resolves the profile to an env-var name (and then to the actual key) at call time; this
resolution never happens inside `execute`/`compile_to_code` (ADR 0002 purity — reading
`connections.toml` is I/O).

## 5. Eval Runs (Prompt Lab)

`ef.eval.run` runs one prompt template over every combination of a dataset of variable
bindings and a list of model variants, returning a tidy DataFrame — one row per
`(input_row, variant)`:

```python
results = ef.eval.run(
    system="You are a sentiment classifier.",
    user="Classify: {{text}}",
    dataset=[
        {"text": "I love this product!"},
        {"text": "Terrible experience."},
        {"text": "It's okay, nothing special."},
    ],
    variants=[
        {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        {"provider": "openai", "model": "gpt-4o"},
    ],
    client=client,
)
print(results)  # columns: row_id, input, messages, provider, model, output,
                #          input_tokens, output_tokens, cost_usd, latency_ms, finish_reason
```

Each dataset row is rendered fresh against `system`/`user` (same `{{var}}` rules as
`ef.llm.prompt`), then called once per variant. A variant dict requires `provider` and `model`
and may add any of `ef.llm.call`'s other keyword arguments (`temperature`, `max_tokens`,
`response_format`, `response_schema`, `api_key_env`, `llm_connection`) — passed straight
through. `client` is required (no default) and, under a `ReplayClient`, makes the whole run
deterministic since fixtures are keyed by each rendered request's content hash.

## 6. Labeling & Export

`ef.eval.label` left-merges human labels onto `ef.eval.run`'s results, joined on
`(row_id, variant)` where `variant` is derived as `"{provider}:{model}"`. `labels_df` needs
`row_id`, `variant`, and `label` columns (plus optional `score`, `rubric`, `note`):

```python
import pandas as pd

labels_df = pd.DataFrame({
    "row_id": [0, 1, 2],
    "variant": ["anthropic:claude-sonnet-4-20250514"] * 3,
    "label": ["positive", "negative", "neutral"],
})
labeled = ef.eval.label(results, labels_df)

# Export as eval set (JSONL) -- only labeled rows are written
manifest = ef.eval.export_eval_set(labeled, path="eval_set.jsonl")

# Export as fine-tune dataset (each row's messages + an appended assistant reply)
manifest = ef.eval.export_finetune(labeled, path="finetune.jsonl")
```

Both exporters silently drop rows with no label (an eval/fine-tune set is *judged* data) and
return a `DatasetExportManifest` (`path`, `row_count`, `byte_size`) describing what was written.

## 7. Client Injection in Graphs

An `llm_call` (or any `requires_client = True`) node needs its client injected at run time,
either into `execute()` or into the compiled module's `main()`:

```python
from emergentflow.ir.serialize import load_graph
from emergentflow.llm.gateway import GatewayClient

graph = load_graph("my_llm_graph.json")

# Execute with client injection
results = ef.execute(graph, client=GatewayClient())

# Compiled code also takes client -- compile_to_code(graph) stays a pure
# function of the graph alone; only the emitted main()'s entry point is
# parametrized by a client
code = ef.compile_to_code(graph)
# The emitted module's main() takes client: main(client=GatewayClient())
```

## 8. Testing with ReplayClient

`ReplayClient` replays a recorded `LLMResponse` keyed by the requesting `LLMRequest`'s content
hash, and never touches the network — it's the default client in tests and the ADR-0002
equivalence gate:

```python
from emergentflow.llm.replay import ReplayClient

client = ReplayClient(fixtures_dir="tests/fixtures/llm")
response = ef.llm.call(messages, provider="anthropic", model="claude-sonnet-4-20250514", client=client)
```

If no fixture exists for a request's content hash, `ReplayClient.complete` raises
`FixtureMissError` with the hash and a copy-pasteable `write_fixture(...)` call to record one
(`emergentflow.llm.replay.write_fixture(fixtures_dir, request, response)`).

## 9. In the Canvas

> **In the Canvas:** Add an `llm_prompt` node to render a template, then connect its output to
> an `llm_call` node. Configure the provider, model, and connection in the Config tab. For
> structured output, set `response_format` to `"json"` and provide a schema. The Prompt Lab
> (accessible from the toolbar) lets you run eval comparisons across multiple models
> interactively. See [Canvas UI Guide](canvas-ui-guide.md).
